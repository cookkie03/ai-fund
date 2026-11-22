"""Comandi del Portafoglio: update_risk_limits, close_position, modify_exit (con eventi al commit)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from bootstrap import build_test_office
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


@pytest.fixture
def env(tmp_path):
    db = OfficeDB(tmp_path / "pc.db")
    broker = FakeBracketBroker(market_prices={"AAPL": Decimal("105")})
    office = build_test_office(db=db, broker=broker)
    rt = Runtime(office=office)
    client = TestClient(create_app(rt, token=None, host="127.0.0.1"))
    sub = rt.bus.subscribe()
    yield {"rt": rt, "db": db, "broker": broker, "client": client, "sub": sub}
    sub.unsubscribe()


def seed_trade(env, ticker="AAPL", qty=100, entry=100.0, stop=95.0, target=120.0, price=105.0):
    db, broker = env["db"], env["broker"]
    draft = {"symbol": ticker, "side": "buy", "entry": str(entry), "stop": str(stop),
             "take_profit": str(target), "quantity": str(qty)}
    oid = db.insert_order(ticker=ticker, side="buy", draft=draft, draft_hash=uuid.uuid4().hex,
                          approval_status="approved", client_order_id=f"seed-{uuid.uuid4().hex[:6]}",
                          status="submitted")
    bid = broker.submit_bracket(f"seed-{oid}", ticker, "buy", Decimal(qty), Decimal(str(entry)),
                                Decimal(str(target)), Decimal(str(stop)))
    db.update_order_status(oid, status="submitted", broker_order_id=bid)
    with db.transaction():
        tid = env["rt"].office.order_flow.trade_manager.record_entry_fill(
            order_id=oid, fill_price=entry, qty=qty, stop_loss=stop)
    db.connection.execute(
        "INSERT OR REPLACE INTO securities(symbol, name, sector) VALUES (?,?,?)",
        (ticker, ticker, "Tech"))
    db.insert_portfolio_snapshot(
        equity=100000.0, cash=50000.0, ts="2026-11-22T10:00:00+00:00",
        positions=[{"symbol": ticker, "qty": qty, "avg_entry_price": entry,
                    "current_price": price, "market_value": qty * price,
                    "unrealized_pl": (price - entry) * qty}])
    return tid


def drain(sub):
    out = []
    while not sub._queue.empty():
        out.append(sub._queue.get_nowait())
    return out


def post(client, name, body, key=None):
    return client.post(f"/v1/commands/{name}", json=body,
                       headers={"Idempotency-Key": key or str(uuid.uuid4()), "X-Actor": "luca"})


# --- update_risk_limits ---------------------------------------------------------------------

def test_update_risk_limits_versions_inbox_event_and_gate(env):
    res = post(env["client"], "update_risk_limits",
               {"limits": {"max_position_fraction": 0.05}, "reason": "più prudente",
                "confirm": True}).json()
    assert res["ok"] and res["data"]["version"] == 1
    types = [e.type for e in drain(env["sub"])]
    assert "risk_limits.updated" in types
    assert env["rt"].office.build_risk_gate_context().limits.max_position_size == Decimal("0.05")
    hist = env["client"].get("/v1/read/risk_limits_history").json()
    assert hist[0]["actor"] == "luca" and hist[0]["reason"] == "più prudente"
    cur = env["client"].get("/v1/read/risk_limits").json()
    assert cur["version"] == 1 and cur["limits"]["max_position_fraction"] == 0.05
    assert "max_position_fraction" in cur["bounds"]


def test_update_risk_limits_out_of_bounds_rejected_with_reasons(env):
    res = post(env["client"], "update_risk_limits",
               {"limits": {"max_risk_per_trade_fraction": 0.5}, "reason": "x", "confirm": True}).json()
    assert res["ok"] is False and res["reasons"]
    assert env["client"].get("/v1/read/risk_limits").json()["version"] == 0
    assert "risk_limits.updated" not in [e.type for e in drain(env["sub"])]


def test_update_risk_limits_requires_confirm(env):
    r = env["client"].post("/v1/commands/update_risk_limits",
                           json={"limits": {"max_open_positions": 5}, "reason": "x"})
    assert r.status_code == 422


def test_update_risk_limits_idempotent(env):
    body = {"limits": {"max_open_positions": 12}, "reason": "ok", "confirm": True}
    a = post(env["client"], "update_risk_limits", body, key="k1").json()
    b = post(env["client"], "update_risk_limits", body, key="k1").json()
    assert a == b
    assert env["client"].get("/v1/read/risk_limits").json()["version"] == 1


# --- close_position -------------------------------------------------------------------------

def test_close_position_total_closes_trade_and_emits_events(env):
    tid = seed_trade(env)
    drain(env["sub"])
    res = post(env["client"], "close_position",
               {"ticker": "AAPL", "qty": None, "order_type": "market", "confirm": True}).json()
    assert res["ok"], res
    assert res["data"]["order"]["status"] == "filled" and res["data"]["order"]["side"] == "sell"
    trade = env["db"].get_trade(tid)
    assert trade["closed_ts"] is not None and trade["exit_reason"] == "pm_sell"
    assert trade["realized_pnl"] == pytest.approx(500.0)
    types = [e.type for e in drain(env["sub"])]
    assert "order.created" in types and "trade.closed" in types
    assert "position.changed" in types and "portfolio.updated" in types


def test_close_position_partial_reduces_and_keeps_residual_protection(env):
    tid = seed_trade(env)
    res = post(env["client"], "close_position",
               {"ticker": "AAPL", "qty": 40, "order_type": "market", "confirm": True}).json()
    assert res["ok"], res
    trade = env["db"].get_trade(tid)
    assert trade["closed_ts"] is None
    assert trade["closed_qty"] == 40 and trade["realized_pnl"] == pytest.approx(200.0)
    assert env["broker"].closed_positions[0]["qty"] == Decimal("40")
    pos = env["client"].get("/v1/read/positions").json()
    assert pos[0]["qty"] == 60 and pos[0]["stop_price"] == 95.0
    # chiudere di nuovo più della quantità residua è bloccato
    again = post(env["client"], "close_position",
                 {"ticker": "AAPL", "qty": 61, "order_type": "market", "confirm": True}).json()
    assert again["ok"] is False and again["reasons"]


def test_close_position_idempotent(env):
    seed_trade(env)
    body = {"ticker": "AAPL", "qty": 10, "order_type": "market", "confirm": True}
    a = post(env["client"], "close_position", body, key="same").json()
    b = post(env["client"], "close_position", body, key="same").json()
    assert a == b
    assert len(env["broker"].closed_positions) == 1


def test_close_position_blocked_in_halt(env):
    tid = seed_trade(env)
    post(env["client"], "halt", {"cancel_open": False, "confirm": True})
    res = post(env["client"], "close_position",
               {"ticker": "AAPL", "qty": None, "order_type": "market", "confirm": True}).json()
    assert res["ok"] is False and "halted" in res["reasons"][0]
    assert env["db"].get_trade(tid)["closed_ts"] is None and not env["broker"].closed_positions


def test_close_position_unknown_ticker(env):
    res = post(env["client"], "close_position",
               {"ticker": "ZZZZ", "qty": None, "order_type": "market", "confirm": True}).json()
    assert res["ok"] is False


def test_close_position_dry_run_writes_nothing(env):
    tid = seed_trade(env)
    drain(env["sub"])
    before = env["db"].connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    res = post(env["client"], "close_position",
               {"ticker": "AAPL", "qty": 40, "order_type": "market", "dry_run": True}).json()
    assert res["ok"] and res["data"]["qty"] == 40
    assert res["data"]["estimated_value"] == pytest.approx(4200.0)
    assert res["data"]["estimated_realized_pnl"] == pytest.approx(200.0)
    assert res["data"]["risk_gate"]["allowed"] is True
    after = env["db"].connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert after == before and not drain(env["sub"])
    assert env["db"].get_trade(tid)["closed_qty"] == 0
    assert env["db"].connection.execute("SELECT COUNT(*) FROM orders WHERE side='sell'").fetchone()[0] == 0


def test_close_position_limit_requires_price(env):
    seed_trade(env)
    r = env["client"].post("/v1/commands/close_position",
                           json={"ticker": "AAPL", "order_type": "limit", "confirm": True})
    assert r.status_code == 422


# --- modify_exit ----------------------------------------------------------------------------

def test_modify_exit_tighten_ok_updates_broker_trade_and_event(env):
    tid = seed_trade(env)
    drain(env["sub"])
    res = post(env["client"], "modify_exit",
               {"ticker": "AAPL", "stop_price": 100.0, "target_price": 125.0, "confirm": True}).json()
    assert res["ok"], res
    t = env["db"].get_trade(tid)
    assert t["stop_price"] == 100.0 and t["target_price"] == 125.0
    assert env["broker"].modified_stops[-1][1] == Decimal("100.0")
    evs = drain(env["sub"])
    pc = [e for e in evs if e.type == "position.changed"]
    assert pc and pc[0].payload["change"] == "exit_levels"


def test_modify_exit_widen_beyond_limit_rejected_with_reasons(env):
    tid = seed_trade(env)
    # rischio 100 * (105-60) = 4500 > 1% di 100000
    res = post(env["client"], "modify_exit",
               {"ticker": "AAPL", "stop_price": 60.0, "confirm": True}).json()
    assert res["ok"] is False and res["reasons"]
    assert env["db"].get_trade(tid)["stop_price"] == 95.0
    assert not env["broker"].modified_stops


def test_modify_exit_widen_within_limit_allowed(env):
    tid = seed_trade(env)
    # rischio 100 * (105-96)... allargare da 95 a 94: 1100 > 1000 => alza limite
    post(env["client"], "update_risk_limits",
         {"limits": {"max_risk_per_trade_fraction": 0.02}, "reason": "più spazio", "confirm": True})
    res = post(env["client"], "modify_exit",
               {"ticker": "AAPL", "stop_price": 94.0, "confirm": True}).json()
    assert res["ok"], res
    assert env["db"].get_trade(tid)["stop_price"] == 94.0


def test_modify_exit_invalid_levels_rejected(env):
    seed_trade(env)
    r1 = post(env["client"], "modify_exit", {"ticker": "AAPL", "stop_price": 110.0, "confirm": True}).json()
    assert r1["ok"] is False
    r2 = post(env["client"], "modify_exit", {"ticker": "AAPL", "target_price": 101.0, "confirm": True}).json()
    assert r2["ok"] is False


def test_modify_exit_allowed_in_halt_when_tightening(env):
    tid = seed_trade(env)
    post(env["client"], "halt", {"cancel_open": False, "confirm": True})
    res = post(env["client"], "modify_exit", {"ticker": "AAPL", "stop_price": 99.0, "confirm": True}).json()
    assert res["ok"], res
    assert env["db"].get_trade(tid)["stop_price"] == 99.0


def test_modify_exit_dry_run_reports_risk_and_writes_nothing(env):
    tid = seed_trade(env)
    before = env["db"].connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    res = post(env["client"], "modify_exit",
               {"ticker": "AAPL", "stop_price": 60.0, "dry_run": True}).json()
    assert res["ok"] and res["data"]["risk_gate"]["allowed"] is False
    assert res["data"]["open_risk"] == pytest.approx(4500.0)
    assert env["db"].connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before
    assert env["db"].get_trade(tid)["stop_price"] == 95.0


def test_events_not_published_when_close_rolls_back(env):
    """Gli eventi di dominio vanno sul bus solo al commit: un errore del broker non ne pubblica."""
    seed_trade(env)
    drain(env["sub"])
    env["broker"].market_prices.clear()  # il broker finto solleva: nessuna chiusura
    res = post(env["client"], "close_position",
               {"ticker": "AAPL", "qty": None, "order_type": "market", "confirm": True}).json()
    assert res["ok"] is False
    types = [e.type for e in drain(env["sub"])]
    assert "trade.closed" not in types and "position.changed" not in types


def test_closed_position_disappears_even_if_snapshot_is_stale(env):
    seed_trade(env)
    post(env["client"], "close_position",
         {"ticker": "AAPL", "qty": None, "order_type": "market", "confirm": True})
    assert env["client"].get("/v1/read/positions").json() == []
    assert env["client"].get("/v1/read/portfolio_summary").json()["positions_count"] == 0


def _stream_sell(env, client_order_id, qty, price, ts):
    env["rt"].office.order_flow.apply_broker_update({
        "event": "fill", "price": price, "qty": qty, "timestamp": ts,
        "order": {"id": f"brk-{client_order_id}", "client_order_id": client_order_id,
                  "symbol": "AAPL", "side": "sell"}})


def test_stream_fill_of_manual_close_is_not_applied_twice(env):
    tid = seed_trade(env)
    res = post(env["client"], "close_position",
               {"ticker": "AAPL", "qty": 30, "order_type": "market", "confirm": True}).json()
    cid = res["data"]["order"]["client_order_id"]
    _stream_sell(env, cid, 30, 105.0, "2026-11-22T11:00:00Z")  # eco dello stream: già registrato
    t = env["db"].get_trade(tid)
    assert t["closed_qty"] == 30 and t["realized_pnl"] == pytest.approx(150.0)


def test_stream_fill_of_pending_manual_sell_reduces_or_closes(env):
    """Broker reale: la vendita parte 'submitted' e il fill arriva dallo stream."""
    tid = seed_trade(env)
    db = env["db"]
    for qty, expect_closed in ((40, False), (60, True)):
        cid = f"manual-{qty}"
        db.insert_order(ticker="AAPL", side="sell", draft={"symbol": "AAPL", "side": "sell"},
                        draft_hash=cid, approval_status="approved", client_order_id=cid,
                        status="submitted")
        _stream_sell(env, cid, qty, 110.0, f"2026-11-22T{qty // 4}:00:00Z")
        t = db.get_trade(tid)
        assert (t["closed_ts"] is not None) is expect_closed
    assert t["exit_reason"] == "pm_sell" and t["realized_pnl"] == pytest.approx(1000.0)
