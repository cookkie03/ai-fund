"""Tests for TradeManager: trade lifecycle from entry to exit with events and trailing stop."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from execution.order_draft import OrderDraftInputs, build_order_draft
from execution.order_flow import OrderFlow
from execution.risk_gate import RiskGateContext
from execution.trade_manager import TradeManager
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


@pytest.fixture
def db(tmp_path) -> OfficeDB:
    return OfficeDB(tmp_path / "office_test.db")


@pytest.fixture
def broker() -> FakeBracketBroker:
    return FakeBracketBroker()


@pytest.fixture
def submitted_buy_order_id(db, broker) -> int:
    """Helper fixture to create a submitted buy order in the database and broker."""
    inputs = OrderDraftInputs(
        symbol="MSFT",
        side="buy",
        current_price=Decimal("50.0"),
        atr=Decimal("3.0"),
        equity=Decimal("100000.0"),
        risk_fraction=Decimal("0.01"),
        k_entry=Decimal("0.5"),
        k_stop=Decimal("2.0"),
        k_tp=Decimal("3.0"),
    )
    draft = build_order_draft(inputs)
    ctx = RiskGateContext(
        equity=Decimal("100000.0"),
        cash=Decimal("50000.0"),
        positions={},
        sector_map={"MSFT": "Technology"},
        open_positions_count=0,
    )
    flow = OrderFlow(db=db, broker=broker, approval_mode="auto")
    outcome = flow.process_accepted_order("MSFT", "accept", draft, ctx)
    assert outcome.is_submitted
    return outcome.order_id


def test_record_entry_fill_creates_trade_and_trailing_state(db, broker, submitted_buy_order_id):
    """Stories 70, 72: On entry fill, records Trade from entry with initial events and trailing state."""
    tm = TradeManager(db=db, broker=broker)

    trade_id = tm.record_entry_fill(
        order_id=submitted_buy_order_id,
        fill_price=Decimal("48.5"),
        qty=Decimal("166"),
        atr=Decimal("3.0"),
        k_trail_act=Decimal("1.5"),
        k_trail=Decimal("1.0"),
        stop_loss=Decimal("42.5"),
    )
    assert trade_id is not None

    # Verify Trade in DB
    trade = db.get_trade(trade_id)
    assert trade is not None
    assert trade["ticker"] == "MSFT"
    assert trade["entry_order_id"] == submitted_buy_order_id
    assert trade["entry_price"] == 48.5
    assert trade["qty"] == 166.0
    assert trade["closed_ts"] is None
    assert trade["exit_reason"] is None

    events = json.loads(trade["events_json"])
    assert len(events) == 1
    assert events[0]["event"] == "entry_filled"
    assert events[0]["price"] == 48.5

    # Verify order updated to filled
    order = db.get_order(submitted_buy_order_id)
    assert order["status"] == "filled"

    # Verify order_event recorded
    order_events = db.list_order_events(submitted_buy_order_id)
    assert any(e["event"] == "filled" for e in order_events)

    # Verify inbox entry recorded
    inbox = db.list_inbox()
    assert any(
        item["kind"] == "order_executed" and "MSFT" in item["text"] for item in inbox
    )

    # Trailing state initialized
    state = tm.get_trailing_state("MSFT")
    assert state is not None
    assert state.entry == Decimal("48.5")
    assert state.atr == Decimal("3.0")
    assert state.active is False
    assert state.stop == Decimal("42.5")


def test_trailing_stop_activation_and_modification(db, broker, submitted_buy_order_id):
    """Stories 72-74: on_price updates trailing stop, calls broker.modify_stop, appends event (no LLM)."""
    tm = TradeManager(db=db, broker=broker)

    # Entry = 50, ATR = 3, k_trail_act = 1.5, k_trail = 1.0, stop = 44
    # Activation threshold = 50 + 1.5 * 3 = 54.5
    trade_id = tm.record_entry_fill(
        order_id=submitted_buy_order_id,
        fill_price=Decimal("50.0"),
        qty=Decimal("100"),
        atr=Decimal("3.0"),
        k_trail_act=Decimal("1.5"),
        k_trail=Decimal("1.0"),
        stop_loss=Decimal("44.0"),
    )

    # 1. Price below activation: price = 53 (< 54.5)
    res1 = tm.on_price("MSFT", Decimal("53.0"))
    assert res1 is not None
    assert res1.state.active is False
    assert res1.stop_changed is False
    assert res1.state.stop == Decimal("44.0")
    assert len(broker.modified_stops) == 0

    # 2. Price hits activation: price = 55 (>= 54.5)
    # Stop moves to break-even (50.0) or highest - 1.0*3 (55 - 3 = 52.0) -> max(44, 50, 52) = 52.0
    res2 = tm.on_price("MSFT", Decimal("55.0"))
    assert res2 is not None
    assert res2.state.active is True
    assert res2.stop_changed is True
    assert res2.state.stop == Decimal("52.0")

    # Verify broker.modify_stop was called
    assert len(broker.modified_stops) == 1
    broker_order = broker.get_order(db.get_order(submitted_buy_order_id)["broker_order_id"])
    assert broker_order.stop_loss == Decimal("52.0")

    # Verify trailing event appended in DB trade
    trade = db.get_trade(trade_id)
    events = json.loads(trade["events_json"])
    assert any(
        e["event"] == "trailing_stop_updated" and e["new_stop"] == 52.0 for e in events
    )

    # 3. Price drops to 53.5: stop never lowered
    res3 = tm.on_price("MSFT", Decimal("53.5"))
    assert res3 is not None
    assert res3.stop_changed is False
    assert res3.state.stop == Decimal("52.0")
    assert len(broker.modified_stops) == 1  # No new call

    # 4. Price rises further to 58:
    # highest = 58, trail_target = 58 - 3 = 55 > 52 -> stop moves to 55
    res4 = tm.on_price("MSFT", Decimal("58.0"))
    assert res4 is not None
    assert res4.stop_changed is True
    assert res4.state.stop == Decimal("55.0")
    assert len(broker.modified_stops) == 2
    assert broker.modified_stops[-1][1] == Decimal("55.0")


def test_on_price_returns_none_for_unknown_ticker(db, broker):
    """Unknown ticker without an open trade returns None."""
    tm = TradeManager(db=db, broker=broker)
    assert tm.on_price("UNKNOWN", Decimal("100.0")) is None


@pytest.mark.parametrize("exit_reason", ["tp", "sl", "pm_sell", "expired"])
def test_record_exit_fill_all_reasons(db, broker, submitted_buy_order_id, exit_reason):
    """Story 71: Record exit for TP, SL, PM sell, or expiration with prices and times."""
    tm = TradeManager(db=db, broker=broker)

    trade_id = tm.record_entry_fill(
        order_id=submitted_buy_order_id,
        fill_price=Decimal("200.0"),
        qty=Decimal("100"),
        atr=Decimal("4.0"),
    )

    tm.record_exit_fill(
        trade_id=trade_id,
        exit_price=Decimal("210.0"),
        exit_reason=exit_reason,
        ts="2026-11-18T15:30:00Z",
    )

    trade = db.get_trade(trade_id)
    assert trade["closed_ts"] == "2026-11-18T15:30:00Z"
    assert trade["exit_price"] == 210.0
    assert trade["exit_reason"] == exit_reason

    events = json.loads(trade["events_json"])
    assert any(e["event"] == f"exit_{exit_reason}" for e in events)

    # Active trailing state cleaned up
    assert tm.get_trailing_state("MSFT") is None

    # Subsequent on_price returns None
    assert tm.on_price("MSFT", Decimal("215.0")) is None


def test_trade_manager_state_reconstruction_on_restart(db, broker, submitted_buy_order_id):
    """Story 70: State recovery after restart from persistent database."""
    tm1 = TradeManager(db=db, broker=broker)

    trade_id = tm1.record_entry_fill(
        order_id=submitted_buy_order_id,
        fill_price=Decimal("200.0"),
        qty=Decimal("100"),
        atr=Decimal("4.0"),
        k_trail_act=Decimal("1.5"),
        k_trail=Decimal("1.0"),
        stop_loss=Decimal("192.0"),
    )

    # Advance price past activation in tm1
    tm1.on_price("MSFT", Decimal("208.0"))

    # Simulate restart: new TradeManager instance pointing to same DB
    tm2 = TradeManager(db=db, broker=broker)
    state = tm2.get_trailing_state("MSFT")
    assert state is not None
    assert state.entry == Decimal("200.0")
    assert state.active is True
    assert state.stop == Decimal("204.0")  # 208 - 4 = 204

    # Further price move continues seamlessly
    res = tm2.on_price("MSFT", Decimal("215.0"))
    assert res.stop_changed is True
    assert res.state.stop == Decimal("211.0")


def test_trade_query_helpers(db, broker, submitted_buy_order_id):
    """Story 75: View open and closed trades."""
    tm = TradeManager(db=db, broker=broker)

    trade_id = tm.record_entry_fill(
        order_id=submitted_buy_order_id,
        fill_price=Decimal("200.0"),
        qty=Decimal("100"),
    )

    # Query open trade
    open_trade = tm.get_open_trade("MSFT")
    assert open_trade is not None
    assert open_trade["id"] == trade_id

    # List trades
    all_trades = tm.list_trades()
    assert len(all_trades) == 1
    assert all_trades[0]["id"] == trade_id

    open_trades = tm.list_trades(open_only=True)
    assert len(open_trades) == 1

    # Close trade
    tm.record_exit_fill(trade_id, Decimal("210.0"), "tp")

    assert tm.get_open_trade("MSFT") is None
    assert len(tm.list_trades(open_only=True)) == 0
    assert len(tm.list_trades(open_only=False)) == 1
