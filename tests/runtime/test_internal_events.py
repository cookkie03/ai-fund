from datetime import UTC, datetime
from decimal import Decimal

import pytest

from agents.fake_backend import ScriptedBackend
from bootstrap import build_test_office
from execution.order_draft import OrderDraftInputs, build_order_draft
from execution.order_flow import OrderFlow, SystemHalt
from execution.risk_gate import RiskGateContext
from execution.trade_manager import TradeManager
from runtime.events import EventBus, EventLog
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker
from workflows.scheduling import ScheduledTask, TaskSource


@pytest.fixture
def db(tmp_path):
    return OfficeDB(tmp_path / "test_events.db")


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def event_log(db, bus):
    return EventLog(db=db, bus=bus)


def test_halt_events(db, event_log):
    halt = SystemHalt(db=db, event_log=event_log)
    halt.halt(cancel_open=False)

    events = event_log.since(0)
    assert any(e.type == "halt.changed" and e.payload.get("halted") is True for e in events)

    halt.resume()
    events2 = event_log.since(0)
    assert any(e.type == "halt.changed" and e.payload.get("halted") is False for e in events2)


def test_order_flow_events(db, event_log):
    broker = FakeBracketBroker()
    of = OrderFlow(db=db, broker=broker, event_log=event_log, approval_mode="manual")

    inputs = OrderDraftInputs(
        symbol="AAPL",
        side="buy",
        current_price=Decimal("150.0"),
        atr=Decimal("2.0"),
        equity=Decimal("100000.0"),
        risk_fraction=Decimal("0.001"),
        k_entry=Decimal("0.0"),
        k_stop=Decimal("2.0"),
        k_tp=Decimal("3.0"),
    )
    draft = build_order_draft(inputs)
    ctx = RiskGateContext(
        equity=Decimal("100000.0"),
        cash=Decimal("100000.0"),
    )

    outcome = of.process_accepted_order(
        ticker="AAPL",
        action="buy",
        draft=draft,
        ctx=ctx,
        client_order_id="c_test_events_1",
    )
    assert outcome.status == "pending"

    events = event_log.since(0)
    created_events = [e for e in events if e.type == "order.created"]
    assert len(created_events) == 1
    assert created_events[0].payload["ticker"] == "AAPL"

    # Approve
    order_id = outcome.order_id
    of.approve(order_id)
    events = event_log.since(0)
    assert any(e.type == "order.approved" and e.payload["order_id"] == order_id for e in events)


def test_trade_manager_events(db, event_log):
    broker = FakeBracketBroker()
    tm = TradeManager(db=db, broker=broker, event_log=event_log)

    order_id = db.insert_order(
        ticker="MSFT",
        side="buy",
        draft={"qty": 10.0, "limit_price": 300.0},
        draft_hash="h1",
        approval_status="approved",
        client_order_id="c_msft_1",
        status="filled",
    )

    trade_id = tm.record_entry_fill(
        ticker="MSFT",
        entry_order_id=order_id,
        entry_price=Decimal("300.0"),
        qty=Decimal("10.0"),
        opened_ts="2026-11-20T10:00:00Z",
    )

    events = event_log.since(0)
    open_events = [e for e in events if e.type == "trade.opened"]
    assert len(open_events) == 1
    assert open_events[0].payload["trade_id"] == trade_id
    assert open_events[0].payload["ticker"] == "MSFT"

    tm.record_exit_fill(
        ticker="MSFT",
        exit_price=Decimal("320.0"),
        exit_reason="tp",
        closed_ts="2026-11-20T11:00:00Z",
        exit_order_id=order_id + 1,
    )

    events2 = event_log.since(0)
    close_events = [e for e in events2 if e.type == "trade.closed"]
    assert len(close_events) == 1
    assert close_events[0].payload["trade_id"] == trade_id
    assert close_events[0].payload["exit_reason"] == "tp"


def test_office_deliver_cycle_events(db, event_log):
    # Setup test office with scripted responses that immediately decide
    pm_response = {
        "content": "Decision: rimando. Ticker needs more clarity.",
        "tool_calls": [],
    }
    backend = ScriptedBackend({"Portfolio Manager": [pm_response]})
    office = build_test_office(db=db, backend=backend, clock=datetime(2026, 11, 20, 10, 0, 0, tzinfo=UTC))
    office.event_log = event_log

    task = ScheduledTask(
        task_id="1",
        agent="Portfolio Manager",
        chat="AAPL",
        when=datetime(2026, 11, 20, 10, 0, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="Test cycle events",
    )

    office.deliver(task)

    events = event_log.since(0)
    event_types = [e.type for e in events]
    assert "cycle.opened" in event_types
    assert "cycle.closed" in event_types
    assert "task.delivered" in event_types
