"""Tests for OfficeDB repository and SQLite migrations."""

import sqlite3
from pathlib import Path

import pytest

from storage.office_db import OfficeDB


@pytest.fixture
def db(tmp_path: Path) -> OfficeDB:
    db_path = tmp_path / "test_office.db"
    office_db = OfficeDB(db_path)
    yield office_db
    office_db.close()


def test_migrations_and_pragmas(db: OfficeDB) -> None:
    assert db.schema_version >= 1
    # Check WAL mode
    journal_mode = db.connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal_mode.lower() == "wal"
    # Check foreign keys
    foreign_keys = db.connection.execute("PRAGMA foreign_keys").fetchone()[0]
    assert foreign_keys == 1

    # Idempotent migrations
    initial_version = db.schema_version
    db._migrate()
    assert db.schema_version == initial_version


def test_chat_and_message_lifecycle(db: OfficeDB) -> None:
    chat_id = db.create_chat("pm", "AAPL")
    assert chat_id > 0
    # Duplicate chat creation returns existing ID
    assert db.create_chat("pm", "AAPL") == chat_id

    chat = db.get_chat(chat_id)
    assert chat is not None
    assert chat["agent"] == "pm"
    assert chat["topic"] == "AAPL"

    msg1_id = db.append_message(chat_id, author="pm", text="Open analysis", kind="original")
    msg2_id = db.append_message(chat_id, author="technical", text="Bullish setup", kind="original")

    msgs = db.list_messages(chat_id)
    assert len(msgs) == 2
    assert msgs[0]["id"] == msg1_id
    assert msgs[1]["id"] == msg2_id

    # Compaction inserts summary row but preserves originals
    summary_id = db.compact_chat(chat_id, summary_text="Cycle 1: Bullish setup confirmed")
    all_msgs = db.list_messages(chat_id)
    assert len(all_msgs) == 3
    assert any(m["id"] == summary_id and m["kind"] == "summary" for m in all_msgs)

    # Filtering by kind
    originals = db.list_messages(chat_id, kind="original")
    assert len(originals) == 2
    summaries = db.list_messages(chat_id, kind="summary")
    assert len(summaries) == 1


def test_scheduled_tasks_lifecycle(db: OfficeDB) -> None:
    t_id = db.enqueue_scheduled_task(
        agent="pm",
        chat="AAPL",
        when_ts="2026-11-18T10:00:00Z",
        source="alert",
        reason="Earnings surprise",
        data={"surprise": 0.15},
    )
    assert t_id > 0

    # Due tasks
    due = db.due_scheduled_tasks(now_ts="2026-11-18T10:05:00Z")
    assert len(due) == 1
    assert due[0]["id"] == t_id

    # Not due in the past
    not_due = db.due_scheduled_tasks(now_ts="2026-11-18T09:00:00Z")
    assert len(not_due) == 0

    # Mark delivered
    db.mark_scheduled_task(t_id, status="delivered")
    task = db.get_scheduled_task(t_id)
    assert task is not None
    assert task["status"] == "delivered"
    assert task["attempts"] == 1

    # Merged task
    t2_id = db.enqueue_scheduled_task("pm", "AAPL", "2026-11-18T11:00:00Z", "alert", "Price move")
    db.mark_scheduled_task(t2_id, status="merged", merged_into=t_id)
    task2 = db.get_scheduled_task(t2_id)
    assert task2["status"] == "merged"
    assert task2["merged_into"] == t_id


def test_cycles(db: OfficeDB) -> None:
    cycle_id = db.open_cycle(ticker="NVDA", budget_used={"messages": 1})
    assert cycle_id > 0

    active = db.get_active_cycle("NVDA")
    assert active is not None
    assert active["id"] == cycle_id
    assert active["status"] == "open"

    db.close_cycle(cycle_id, outcome="accept", budget_used={"messages": 8})
    cycle = db.get_cycle(cycle_id)
    assert cycle["status"] == "closed"
    assert cycle["outcome"] == "accept"
    assert "8" in cycle["budget_used_json"]

    assert db.get_active_cycle("NVDA") is None


def test_ticker_state_and_watchlist(db: OfficeDB) -> None:
    state_payload = {"analysis": {"technical": "bullish"}, "k_stop": 2.0}
    db.set_ticker_state("MSFT", state=state_payload)
    retrieved = db.get_ticker_state("MSFT")
    assert retrieved is not None
    assert "bullish" in retrieved["state_json"]

    # Watchlist
    db.add_watchlist("MSFT", note="Tech leader")
    wl = db.list_watchlist()
    assert len(wl) == 1
    assert wl[0]["ticker"] == "MSFT"
    assert wl[0]["note"] == "Tech leader"

    assert db.remove_watchlist("MSFT") is True
    assert len(db.list_watchlist()) == 0


def test_blobs_deduplication_and_compression(db: OfficeDB) -> None:
    text = "Large repeated system prompt " * 100
    h1 = db.put_blob(text)
    h2 = db.put_blob(text)
    assert h1 == h2

    # Exactly one row stored
    row_count = db.connection.execute("SELECT count(*) FROM blobs").fetchone()[0]
    assert row_count == 1

    decompressed = db.get_blob_text(h1)
    assert decompressed == text


def test_orders_events_trades(db: OfficeDB) -> None:
    draft = {"entry": 100.0, "sl": 95.0, "tp": 110.0, "size": 10}
    order_id = db.insert_order(
        ticker="AAPL",
        side="buy",
        draft=draft,
        draft_hash="hash123",
        approval_status="auto",
        client_order_id="order-001",
        status="SUBMITTED",
    )
    assert order_id > 0

    order = db.get_order_by_client_id("order-001")
    assert order is not None
    assert order["id"] == order_id
    assert order["approval_status"] == "auto"

    event_id = db.insert_order_event(order_id, event="submitted_to_broker", detail={"broker": "alpaca"})
    assert event_id > 0
    events = db.list_order_events(order_id)
    assert len(events) == 1
    assert events[0]["event"] == "submitted_to_broker"

    # Trade lifecycle
    trade_id = db.insert_trade(
        ticker="AAPL",
        entry_order_id=order_id,
        entry_price=100.0,
        qty=10.0,
    )
    assert trade_id > 0
    db.close_trade(trade_id, exit_price=110.0, exit_reason="tp")
    trade = db.get_trade(trade_id)
    assert trade["exit_price"] == 110.0
    assert trade["exit_reason"] == "tp"


def test_portfolio_snapshot_and_inbox(db: OfficeDB) -> None:
    db.insert_portfolio_snapshot(equity=100000.0, cash=50000.0, positions=[{"symbol": "AAPL", "qty": 10}])
    snap = db.latest_portfolio_snapshot()
    assert snap is not None
    assert snap["equity"] == 100000.0
    assert snap["cash"] == 50000.0

    # Inbox
    inbox_id = db.add_inbox(kind="risk_gate_block", text="Sector limit exceeded")
    inbox_items = db.list_inbox(unread_only=True)
    assert len(inbox_items) == 1
    assert inbox_items[0]["id"] == inbox_id

    db.mark_inbox_read(inbox_id)
    assert len(db.list_inbox(unread_only=True)) == 0


def test_db_size_and_financial_tables(db: OfficeDB) -> None:
    assert db.db_size_bytes() > 0

    mem_db = OfficeDB(":memory:")
    assert mem_db.db_size_bytes() > 0
    mem_db.close()

    # Test financial data tables existence and schema
    db.connection.execute(
        """
        INSERT INTO securities (symbol, name, sector, industry)
        VALUES ('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics')
        """
    )
    db.connection.execute(
        """
        INSERT INTO prices_ohlcv (symbol, ts, interval, o, h, l, c, v, source, fetched_at)
        VALUES ('AAPL', '2026-11-18T16:00:00Z', '1d', 150.0, 155.0, 149.0, 154.0, 1000000, 'alpaca', '2026-11-18T16:05:00Z')
        """
    )
    db.connection.execute(
        """
        INSERT INTO fundamentals (symbol, source, fetched_at, stale, data_json)
        VALUES ('AAPL', 'openbb', '2026-11-18T16:00:00Z', 0, '{"revenue": 1000}')
        """
    )
    db.connection.execute(
        """
        INSERT INTO ratios (symbol, source, fetched_at, stale, data_json)
        VALUES ('AAPL', 'openbb', '2026-11-18T16:00:00Z', 0, '{"pe": 25.5}')
        """
    )
    db.connection.execute(
        """
        INSERT INTO earnings (symbol, date, source, fetched_at, stale, data_json)
        VALUES ('AAPL', '2026-11-18', 'openbb', '2026-11-18T16:00:00Z', 0, '{"eps": 1.5}')
        """
    )
    db.connection.execute(
        """
        INSERT INTO ratings (symbol, source, fetched_at, stale, data_json)
        VALUES ('AAPL', 'openbb', '2026-11-18T16:00:00Z', 0, '{"buy": 10}')
        """
    )
    db.connection.execute(
        """
        INSERT INTO insider (symbol, transaction_date, source, fetched_at, stale, data_json)
        VALUES ('AAPL', '2026-11-17', 'openbb', '2026-11-18T16:00:00Z', 0, '{"shares": 500}')
        """
    )
    db.connection.execute(
        """
        INSERT INTO news (symbol, headline, summary, full_text, published_at, source, fetched_at, stale)
        VALUES ('AAPL', 'Record Sales', 'Sales high', 'Details...', '2026-11-18T15:00:00Z', 'alpaca', '2026-11-18T16:00:00Z', 0)
        """
    )
    db.connection.execute(
        """
        INSERT INTO macro_series (series_id, ts, value, source, fetched_at, stale)
        VALUES ('FEDFUNDS', '2026-11-01', 5.25, 'fred', '2026-11-18T16:00:00Z', 0)
        """
    )
    db.connection.execute(
        """
        INSERT INTO econ_calendar (event_id, event_name, event_ts, impact, source, fetched_at, stale, data_json)
        VALUES ('evt-1', 'CPI', '2026-11-19T13:30:00Z', 'high', 'fred', '2026-11-18T16:00:00Z', 0, '{}')
        """
    )
    db.connection.execute(
        """
        INSERT INTO sector_performance (sector, ts, perf_json, source, fetched_at, stale)
        VALUES ('Technology', '2026-11-18', '{"1d": 0.015}', 'openbb', '2026-11-18T16:00:00Z', 0)
        """
    )

    row = db.connection.execute("SELECT c FROM prices_ohlcv WHERE symbol = 'AAPL'").fetchone()
    assert row["c"] == 154.0


def test_office_db_validation_and_direct_logging(db: OfficeDB) -> None:
    chat_id = db.create_chat("pm", "AAPL")
    with pytest.raises(ValueError):
        db.append_message(chat_id, author="pm", text="Hi", kind="invalid_kind")

    with pytest.raises(ValueError):
        db.mark_scheduled_task(1, status="invalid_status")

    with pytest.raises(ValueError):
        db.insert_order(
            ticker="AAPL",
            side="buy",
            draft="{}",
            draft_hash="h",
            approval_status="bad_status",
            client_order_id="cid-1",
            status="SUBMITTED",
        )

    with pytest.raises(ValueError):
        db.insert_trade(
            ticker="AAPL",
            entry_order_id=1,
            entry_price=10.0,
            qty=1.0,
            exit_reason="bad_reason",
        )

    # Direct logging methods
    call_id = db.log_llm_call(
        agent="pm",
        model="gpt-4o",
        tokens_in=10,
        tokens_out=20,
        cost=0.001,
        duration_ms=200,
        prompt_text="Very long prompt content",
        response_text="Very long response content",
    )
    assert call_id > 0
    row = db.connection.execute("SELECT prompt_blob, response_blob FROM llm_calls WHERE id = ?", (call_id,)).fetchone()
    assert row["prompt_blob"] is not None
    assert db.get_blob_text(row["prompt_blob"]) == "Very long prompt content"
    assert db.get_blob_text(row["response_blob"]) == "Very long response content"

    tcall_id = db.log_tool_call(agent="market", tool="macro", params={"series": "CPI"}, result={"val": 3.1})
    assert tcall_id > 0

    cmd_id = db.log_cli_command(command="halt", args={"scope": "all"})
    assert cmd_id > 0
