"""Endpoint di lettura del Portafoglio su un DB popolato: contratto JSON e formule."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from bootstrap import build_test_office
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def _iso(d: datetime) -> str:
    return d.isoformat()


def _order(db, ticker, stop, target):
    return db.insert_order(
        ticker=ticker, side="buy",
        draft={"symbol": ticker, "side": "buy", "stop": str(stop), "take_profit": str(target)},
        draft_hash=f"h-{ticker}-{stop}-{target}-{id(object())}", approval_status="approved",
        client_order_id=f"c-{ticker}-{stop}-{target}-{id(object())}", status="filled")


@pytest.fixture
def client(tmp_path):
    db = OfficeDB(tmp_path / "pr.db")
    rt = Runtime(office=build_test_office(db=db, clock=NOW))
    c = TestClient(create_app(rt, token=None, host="127.0.0.1"))
    c.db = db  # type: ignore[attr-defined]
    return c


def seed(db: OfficeDB, *, days: int = 60) -> None:
    for sym, sec in (("AAPL", "Tech"), ("MSFT", "Tech"), ("JNJ", "Health")):
        db.connection.execute(
            "INSERT OR REPLACE INTO securities(symbol, name, sector) VALUES (?,?,?)", (sym, sym, sec))
    # equity e SPY giornalieri
    for i in range(days):
        d = NOW - timedelta(days=days - i)
        eq = 100000 * (1 + 0.001 * i + 0.004 * math.sin(i))
        positions = []
        if i == days - 1:
            positions = [
                {"symbol": "AAPL", "qty": 100, "avg_entry_price": 100.0, "current_price": 110.0,
                 "market_value": 11000.0, "unrealized_pl": 1000.0},
                {"symbol": "MSFT", "qty": 50, "avg_entry_price": 200.0, "current_price": 210.0,
                 "market_value": 10500.0, "unrealized_pl": 500.0},
                {"symbol": "JNJ", "qty": 100, "avg_entry_price": 150.0, "current_price": 140.0,
                 "market_value": 14000.0, "unrealized_pl": -1000.0},
            ]
        cash = eq - 35500.0 if positions else 40000.0
        db.insert_portfolio_snapshot(equity=eq, cash=cash, positions=positions, ts=_iso(d))
        spy = 400 * (1 + 0.0008 * i + 0.003 * math.sin(i + 0.3))
        db.connection.execute(
            "INSERT OR REPLACE INTO prices_ohlcv(symbol, ts, interval, o, h, l, c, v, source, fetched_at)"
            " VALUES ('SPY', ?, '1d', ?, ?, ?, ?, 1, 't', ?)", (_iso(d), spy, spy, spy, spy, _iso(d)))
    # trade aperti
    for sym, qty, entry, stop, target, who in (
        ("AAPL", 100, 100.0, 95.0, 120.0, "market_analyst"),
        ("MSFT", 50, 200.0, 190.0, 240.0, "portfolio_manager"),
        ("JNJ", 100, 150.0, 140.0, 170.0, "market_analyst"),
    ):
        oid = _order(db, sym, stop, target)
        db.insert_trade(ticker=sym, entry_order_id=oid, entry_price=entry, qty=qty,
                        opened_ts=_iso(NOW - timedelta(days=10)), stop_price=stop,
                        target_price=target, initial_stop=stop, proposed_by=who)
    # trade chiusi: (pnl, motivo, agente, giorni fa)
    closed = [(300.0, "tp", "market_analyst", 3), (-100.0, "sl", "market_analyst", 5),
              (200.0, "tp", "portfolio_manager", 8), (-50.0, "sl", "portfolio_manager", 12),
              (120.0, "pm_sell", "market_analyst", 15), (-80.0, "sl", None, 20)]
    for pnl, reason, who, ago in closed:
        oid = _order(db, "AAPL", 95.0 - ago, 120.0 + ago)
        tid = db.insert_trade(ticker="AAPL", entry_order_id=oid, entry_price=100.0, qty=10,
                              opened_ts=_iso(NOW - timedelta(days=ago + 4)), initial_stop=95.0,
                              stop_price=95.0, target_price=120.0, proposed_by=who)
        db.close_trade(tid, exit_price=100.0 + pnl / 10, exit_reason=reason,
                       closed_ts=_iso(NOW - timedelta(days=ago)), realized_pnl=pnl, closed_qty=10)


def test_summary_contract_and_values(client):
    seed(client.db)
    s = client.get("/v1/read/portfolio_summary").json()
    assert set(s) >= {"ts", "equity", "cash", "invested", "cash_reserve_fraction", "day_change",
                      "day_change_fraction", "unrealized_pnl", "realized_pnl_today",
                      "positions_count", "snapshot_age_s", "halted"}
    assert s["positions_count"] == 3 and s["halted"] is False
    assert s["invested"] == pytest.approx(35500.0)
    assert s["unrealized_pnl"] == pytest.approx(500.0)
    assert s["cash_reserve_fraction"] == pytest.approx(s["cash"] / s["equity"])
    assert s["equity"] == pytest.approx(s["cash"] + s["invested"])
    assert s["snapshot_age_s"] == pytest.approx(86400, abs=5)  # ultimo snapshot 1 giorno fa


def test_summary_empty_portfolio_is_zero_not_error(client):
    s = client.get("/v1/read/portfolio_summary").json()
    assert s["equity"] == 0 and s["positions_count"] == 0 and s["ts"] is None


def test_positions_contract_and_open_risk(client):
    seed(client.db)
    rows = {p["ticker"]: p for p in client.get("/v1/read/positions").json()}
    a = rows["AAPL"]
    assert a["side"] == "long" and a["qty"] == 100 and a["sector"] == "Tech"
    assert a["market_value"] == pytest.approx(11000.0)
    assert a["unrealized_pnl"] == pytest.approx(1000.0)
    assert a["unrealized_pnl_fraction"] == pytest.approx(0.10)
    assert a["stop_price"] == 95.0 and a["target_price"] == 120.0
    assert a["open_risk"] == pytest.approx(1500.0)  # (110-95)*100
    assert a["days_held"] == 10 and a["proposed_by"] == "market_analyst"
    equity = client.get("/v1/read/portfolio_summary").json()["equity"]
    assert a["weight"] == pytest.approx(11000.0 / equity)


def test_allocation_sums_to_one_and_limits(client):
    seed(client.db)
    al = client.get("/v1/read/allocation").json()
    total = sum(x["weight"] for x in al["by_position"]) + al["cash"]["weight"]
    assert total == pytest.approx(1.0, abs=1e-6)
    sectors = {x["sector"]: x for x in al["by_sector"]}
    assert sectors["Tech"]["value"] == pytest.approx(21500.0)
    assert sectors["Tech"]["limit"] == 0.30
    assert al["by_position"][0]["limit"] == 0.10
    assert al["cash"]["min_reserve"] == 0.05


def test_performance_metrics_and_benchmark(client):
    seed(client.db)
    p = client.get("/v1/read/performance", params={"period": "3M", "benchmark": "SPY"}).json()
    assert p["period"] == "3M" and p["observations"] >= 50
    assert p["trades_closed"] == 6
    assert p["win_rate"] == pytest.approx(3 / 6)
    assert p["profit_factor"] == pytest.approx(620.0 / 230.0)
    assert p["expectancy"] == pytest.approx(390.0 / 6)
    assert p["realized_pnl"] == pytest.approx(390.0)
    assert p["max_drawdown_fraction"] <= 0 and p["current_drawdown_fraction"] <= 0
    assert p["volatility_annualized"] is not None and p["sharpe"] is not None
    assert p["benchmark"]["ticker"] == "SPY" and p["benchmark"]["beta"] is not None
    assert -1 <= p["benchmark"]["correlation"] <= 1


def test_performance_short_period_reports_insufficient(client):
    seed(client.db)
    p = client.get("/v1/read/performance", params={"period": "1W"}).json()
    assert p["sharpe"] is None and p["volatility_annualized"] is None
    metrics = {i["metric"] for i in p["insufficient"]}
    assert {"sharpe", "volatility_annualized"} <= metrics
    assert all({"metric", "reason", "min_observations"} <= set(i) for i in p["insufficient"])


def test_performance_no_data_all_null_without_error(client):
    p = client.get("/v1/read/performance", params={"period": "ALL"}).json()
    assert p["return_fraction"] is None and p["trades_closed"] == 0 and p["benchmark"] is None


def test_performance_unknown_period_is_422(client):
    assert client.get("/v1/read/performance", params={"period": "5Y"}).status_code == 422


def test_attribution_sums_to_total_pnl(client):
    seed(client.db)
    a = client.get("/v1/read/attribution", params={"period": "ALL"}).json()
    by_pos = {x["ticker"]: x["pnl"] for x in a["by_position"]}
    assert by_pos["AAPL"] == pytest.approx(390.0 + 1000.0)
    total = sum(by_pos.values())
    assert sum(x["pnl"] for x in a["by_sector"]) == pytest.approx(total)
    assert sum(x["pnl"] for x in a["by_agent"]) == pytest.approx(total)
    agents = {x["agent"]: x for x in a["by_agent"]}
    assert "unknown" in agents and agents["market_analyst"]["trades"] >= 3


def test_trades_extended_fields(client):
    seed(client.db)
    rows = client.get("/v1/read/trades", params={"limit": 50}).json()
    closed = [t for t in rows if t.get("closed_ts")]
    t = next(t for t in closed if t["pnl"] == 300.0)
    assert t["exit_reason"] == "tp" and t["proposed_by"] == "market_analyst"
    assert t["r_multiple"] == pytest.approx(300.0 / ((100.0 - 95.0) * 10))
    assert t["duration_s"] == pytest.approx(timedelta(days=4).total_seconds())


def test_equity_history_has_drawdown(client):
    seed(client.db)
    rows = client.get("/v1/read/equity_history").json()
    assert rows and all("drawdown_fraction" in r for r in rows)
    assert all(r["drawdown_fraction"] <= 0 for r in rows)
    assert rows[0]["drawdown_fraction"] == 0


def test_risk_limits_usage_statuses(client):
    seed(client.db)
    rl = client.get("/v1/read/risk_limits").json()
    assert rl["version"] == 0
    usage = {u["limit"]: u for u in rl["usage"]}
    assert usage["max_position_fraction"]["status"] in ("ok", "near", "breach")
    assert usage["max_open_positions"]["current"] == 3
    assert set(rl["bounds"]["max_open_positions"]) == {"min", "max"}
    tech = usage["max_sector_fraction"]
    equity = client.get("/v1/read/portfolio_summary").json()["equity"]
    assert tech["current"] == pytest.approx(21500.0 / equity, abs=1e-6)
