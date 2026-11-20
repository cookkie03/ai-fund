"""Tests for the trading-agent CLI interface (Thin Client over Runtime)."""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from bootstrap import build_test_office
from interface.cli import main
from interface.client import RuntimeClient
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


@pytest.fixture
def test_db(tmp_path) -> OfficeDB:
    return OfficeDB(tmp_path / "test_cli.db")


@pytest.fixture
def fake_broker() -> FakeBracketBroker:
    return FakeBracketBroker()


@pytest.fixture
def runtime(test_db, fake_broker) -> Runtime:
    office = build_test_office(
        db=test_db,
        broker=fake_broker,
        approval_mode="auto",
    )
    return Runtime(office=office)


@pytest.fixture
def test_app(runtime: Runtime):
    return create_app(runtime, host="127.0.0.1")


@pytest.fixture
def client_factory(test_app):
    def _factory() -> RuntimeClient:
        http_client = TestClient(test_app)
        return RuntimeClient(client=http_client)

    return _factory


def run_cli(
    argv: list[str],
    client_factory=None,
    runtime_factory=None,
) -> tuple[int, str]:
    out = io.StringIO()
    code = main(
        argv,
        client_factory=client_factory,
        runtime_factory=runtime_factory,
        out=out,
    )
    return code, out.getvalue()


def test_cli_runtime_unavailable_exits_code_2():
    def _offline_factory():
        return RuntimeClient(base_url="http://127.0.0.1:54321")

    code, out = run_cli(["watchlist", "list"], client_factory=_offline_factory)
    assert code == 2
    assert "Runtime non attivo su http://127.0.0.1:54321: avvialo con 'trading-agent run'" in out


def test_cli_task_enqueues_and_logs_event(client_factory, runtime, test_db):
    code, out = run_cli(["task", "AAPL", "--reason", "Weekly scan"], client_factory=client_factory)
    assert code == 0
    assert "Enqueued manual task" in out
    assert "AAPL" in out

    # Verify scheduled task in DB
    tasks = test_db.due_scheduled_tasks()
    assert len(tasks) == 1
    assert tasks[0]["chat"] == "AAPL"
    assert tasks[0]["source"] == "manual"
    assert tasks[0]["reason"] == "Weekly scan"

    # Verify events log contains task.enqueued
    events = runtime.event_log.since(0)
    assert any(e.type == "task.enqueued" and e.payload["ticker"] == "AAPL" for e in events)


def test_cli_say_to_pm_enqueues_task(client_factory, runtime, test_db):
    code, out = run_cli(
        ["say", "portfolio_manager", "MSFT", "Please check MSFT"],
        client_factory=client_factory,
    )
    assert code == 0
    assert "Message #" in out
    assert "Enqueued manual task" in out

    # Check message
    chat_row = test_db.connection.execute(
        "SELECT id FROM chats WHERE agent = 'portfolio_manager' AND topic = 'MSFT'"
    ).fetchone()
    assert chat_row is not None
    msgs = test_db.list_messages(chat_row["id"])
    assert len(msgs) == 1
    assert msgs[0]["text"] == "Please check MSFT"
    assert msgs[0]["author"] in ("user", "cli")

    # Check task enqueued
    tasks = test_db.due_scheduled_tasks()
    assert any(t["chat"] == "MSFT" and t["agent"] == "portfolio_manager" for t in tasks)


def test_cli_say_to_analyst_does_not_enqueue_task(client_factory, test_db):
    code, out = run_cli(
        ["say", "market_analyst", "macro", "Fed raises rates"],
        client_factory=client_factory,
    )
    assert code == 0
    assert "Message #" in out
    assert "Enqueued manual task" not in out

    tasks = test_db.due_scheduled_tasks()
    assert len(tasks) == 0


def test_cli_watchlist_lifecycle(client_factory):
    # 1. Add
    code, out = run_cli(["watchlist", "add", "NVDA", "--note", "AI leader"], client_factory=client_factory)
    assert code == 0
    assert "Added NVDA" in out

    # 2. List JSON
    code, out = run_cli(["watchlist", "list", "--json"], client_factory=client_factory)
    assert code == 0
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["ticker"] == "NVDA"
    assert data[0]["note"] == "AI leader"

    # Table format list
    code, out_tbl = run_cli(["watchlist", "list"], client_factory=client_factory)
    assert code == 0
    assert "NVDA" in out_tbl

    # 3. Remove
    code, out = run_cli(["watchlist", "remove", "NVDA"], client_factory=client_factory)
    assert code == 0
    assert "Removed NVDA" in out

    # List again
    code, out = run_cli(["watchlist", "list", "--json"], client_factory=client_factory)
    assert code == 0
    data = json.loads(out)
    assert len(data) == 0


def test_cli_cycles_list_and_show(client_factory, test_db):
    cid = test_db.open_cycle(
        ticker="GOOGL",
        status="closed",
        opened_ts="2026-06-01T10:00:00Z",
        budget_used={"messages": 5, "total": 5},
    )
    test_db.close_cycle(cid, outcome="accepted", closed_ts="2026-06-01T10:15:00Z")

    # List
    code, out = run_cli(["cycles", "list", "--json"], client_factory=client_factory)
    assert code == 0
    cycles = json.loads(out)
    assert len(cycles) == 1
    assert cycles[0]["ticker"] == "GOOGL"

    # Show table
    code, out_show = run_cli(["cycles", "show", str(cid)], client_factory=client_factory)
    assert code == 0
    assert f"Cycle #{cid}" in out_show
    assert "GOOGL" in out_show
    assert "accepted" in out_show

    # Show JSON
    code, out_show_json = run_cli(["cycles", "show", str(cid), "--json"], client_factory=client_factory)
    assert code == 0
    data = json.loads(out_show_json)
    assert data["id"] == cid
    assert data["outcome"] == "accepted"


def test_cli_chat_show(client_factory, test_db):
    chat_id = test_db.get_or_create_chat("technical_analyst", "AAPL")
    test_db.append_message(chat_id, "system", "Analyze indicators", "original")
    test_db.append_message(chat_id, "technical_analyst", "RSI is 45, EMA bullish", "original")

    code, out = run_cli(["chat", "show", "technical_analyst", "AAPL", "--json"], client_factory=client_factory)
    assert code == 0
    msgs = json.loads(out)
    assert len(msgs) == 2
    assert msgs[1]["author"] == "technical_analyst"

    code, out_text = run_cli(["chat", "show", "technical_analyst", "AAPL"], client_factory=client_factory)
    assert code == 0
    assert "RSI is 45" in out_text


def test_cli_state_show(client_factory, test_db):
    test_db.set_ticker_state(
        "TSLA",
        state={"analysis": {"technical": "bullish"}, "conviction": 0.8},
        updated_ts="2026-06-01T12:00:00Z",
    )

    code, out = run_cli(["state", "show", "TSLA", "--json"], client_factory=client_factory)
    assert code == 0
    state = json.loads(out)
    assert state["conviction"] == 0.8
    assert state["analysis"]["technical"] == "bullish"

    code, out_text = run_cli(["state", "show", "TSLA"], client_factory=client_factory)
    assert code == 0
    assert "Ticker state for TSLA" in out_text


def test_cli_orders_and_approval(client_factory, test_db):
    # Insert a pending order
    oid = test_db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={
            "symbol": "AAPL",
            "side": "buy",
            "entry": "150.0",
            "stop": "145.0",
            "take_profit": "160.0",
            "quantity": "10",
            "risk_reward": "2.0",
            "notional": "1500.0",
        },
        draft_hash="hash123",
        approval_status="pending",
        client_order_id="cli_order_001",
        status="pending",
    )

    # 1. List
    code, out = run_cli(["orders", "list", "--json"], client_factory=client_factory)
    assert code == 0
    orders = json.loads(out)
    assert len(orders) == 1
    assert orders[0]["client_order_id"] == "cli_order_001"

    # 2. Reject
    code, out = run_cli(["orders", "reject", str(oid), "--reason", "Too risky"], client_factory=client_factory)
    assert code == 0
    assert f"Order #{oid} rejected" in out

    order = test_db.get_order(oid)
    assert order["approval_status"] == "rejected"
    assert order["status"] == "rejected"


def test_cli_trades_list(client_factory, test_db):
    test_db.insert_order(
        ticker="MSFT",
        side="buy",
        draft={"symbol": "MSFT"},
        draft_hash="h1",
        approval_status="approved",
        client_order_id="c_001",
        status="filled",
    )
    _ = test_db.insert_trade(
        ticker="MSFT",
        entry_order_id=1,
        entry_price=300.0,
        qty=10.0,
        opened_ts="2026-06-01T10:00:00Z",
    )

    code, out = run_cli(["trades", "list", "--json"], client_factory=client_factory)
    assert code == 0
    trades = json.loads(out)
    assert len(trades) == 1
    assert trades[0]["ticker"] == "MSFT"
    assert trades[0]["qty"] == 10.0


def test_cli_portfolio_sync(client_factory, test_db):
    code, out = run_cli(["portfolio", "sync", "--json"], client_factory=client_factory)
    assert code == 0
    snapshot = json.loads(out)
    assert "equity" in snapshot
    assert "cash" in snapshot

    # Verify in DB
    db_snap = test_db.latest_portfolio_snapshot()
    assert db_snap is not None
    assert db_snap["equity"] == snapshot["equity"]


def test_cli_inbox(client_factory, test_db):
    iid1 = test_db.add_inbox("risk_block", "Risk Gate blocked order for AAPL")
    iid2 = test_db.add_inbox("halt", "System halted")

    code, out = run_cli(["inbox", "--json"], client_factory=client_factory)
    assert code == 0
    items = json.loads(out)
    assert len(items) == 2

    # Mark read
    code, out = run_cli(["inbox", "--mark-read", str(iid1)], client_factory=client_factory)
    assert code == 0
    assert f"Marked inbox item #{iid1} as read" in out

    # List unread only
    code, out = run_cli(["inbox", "--unread-only", "--json"], client_factory=client_factory)
    assert code == 0
    unread = json.loads(out)
    assert len(unread) == 1
    assert unread[0]["id"] == iid2


def test_cli_halt_and_resume(client_factory, test_db):
    # Halt
    code, out = run_cli(["halt"], client_factory=client_factory)
    assert code == 0
    assert "System halted" in out

    row = test_db.connection.execute("SELECT value FROM system_state WHERE key = 'halted'").fetchone()
    assert row is not None and row["value"] == "1"

    # Resume
    code, out = run_cli(["resume"], client_factory=client_factory)
    assert code == 0
    assert "System resumed" in out

    row = test_db.connection.execute("SELECT value FROM system_state WHERE key = 'halted'").fetchone()
    assert row is not None and row["value"] == "0"


def test_cli_config_check(client_factory):
    code, out = run_cli(["config", "check"], client_factory=client_factory)
    assert code in (0, 1)


def test_cli_help_and_invalid_command(client_factory):
    code, out = run_cli(["--help"], client_factory=client_factory)
    assert code == 0
    assert "usage:" in out

    code, out = run_cli(["nonexistent"], client_factory=client_factory)
    assert code == 2


def test_cli_halt_options(client_factory, test_db):
    code, out = run_cli(["halt", "--no-cancel-open"], client_factory=client_factory)
    assert code == 0
    assert "cancel_open=False" in out

    row = test_db.connection.execute("SELECT value FROM system_state WHERE key = 'halted'").fetchone()
    assert row["value"] == "1"


def test_cli_run_stops_gracefully(runtime):
    import threading
    import time

    out = io.StringIO()
    t = threading.Thread(
        target=main,
        args=(["run", "--poll-interval", "0.05"],),
        kwargs={"runtime_factory": lambda: runtime, "out": out},
    )
    t.start()
    time.sleep(0.1)
    runtime.office.stop()
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert "Starting Agent Office loop" in out.getvalue()
