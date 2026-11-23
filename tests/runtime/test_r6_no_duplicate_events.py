"""Test R6: Commands produce exactly one domain event (no duplicate emissions between handler and domain)."""

from __future__ import annotations

from decimal import Decimal

from bootstrap import build_test_office
from brokers.models import Account
from execution.order_flow import OrderDraft, RiskGateContext
from runtime.commands import ApproveOrder, Halt, RejectOrder, Resume
from runtime.core import Runtime
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker
from tests.fakes.broker import EmptyBroker


def test_r6_halt_and_resume_emit_exactly_one_event_each(tmp_path):
    """Halt and Resume commands must emit exactly one halt.changed event each."""
    db = OfficeDB(tmp_path / "test.db")
    fake_broker = FakeBracketBroker()
    office = build_test_office(db=db, broker=fake_broker)
    rt = Runtime(office=office)

    # Halt
    res = rt.execute(Halt(cancel_open=False, confirm=True), actor="test_user")
    assert res.ok is True
    halt_events = [e for e in rt.event_log.since(0) if e.type == "halt.changed"]
    assert len(halt_events) == 1
    assert halt_events[0].payload.get("halted") is True

    # Resume
    res_resume = rt.execute(Resume(confirm=True), actor="test_user")
    assert res_resume.ok is True
    halt_events_after = [e for e in rt.event_log.since(0) if e.type == "halt.changed"]
    assert len(halt_events_after) == 2  # exactly 1 for halt, 1 for resume
    assert halt_events_after[1].payload.get("halted") is False


def test_r6_approve_order_emits_exactly_one_order_approved_event(tmp_path):
    """ApproveOrder command must emit exactly one order.approved event."""
    db = OfficeDB(tmp_path / "test.db")
    fake_broker = FakeBracketBroker()
    acc = Account(
        id="test",
        status="ACTIVE",
        currency="USD",
        cash=Decimal("50000"),
        equity=Decimal("100000"),
        buying_power=Decimal("100000"),
        trading_blocked=False,
    )
    reader = EmptyBroker(account=acc)
    office = build_test_office(
        db=db,
        broker=fake_broker,
        broker_reader=reader,
        approval_mode="manual",
    )
    draft = OrderDraft(
        symbol="AAPL",
        side="buy",
        quantity=Decimal("10"),
        entry=Decimal("150.0"),
        stop=Decimal("140.0"),
        take_profit=Decimal("170.0"),
        risk_reward=Decimal("2.0"),
        risk_amount=Decimal("100.0"),
        notional=Decimal("1500.0"),
    )
    ctx = RiskGateContext(
        equity=Decimal("100000"),
        cash=Decimal("50000"),
        positions={},
        sector_map={"AAPL": "technology"},
    )
    outcome = office.order_flow.process_accepted_order(
        ticker="AAPL",
        action="BUY",
        draft=draft,
        ctx=ctx,
        client_order_id="cid_r6_approve",
    )
    assert outcome.status == "pending"

    rt = Runtime(office=office)
    res = rt.execute(ApproveOrder(order_id=outcome.order_id, confirm=True), actor="test_user")
    assert res.ok is True

    approved_events = [e for e in rt.event_log.since(0) if e.type == "order.approved"]
    assert len(approved_events) == 1
    assert approved_events[0].payload.get("order_id") == outcome.order_id


def test_r6_reject_order_emits_exactly_one_order_rejected_event(tmp_path):
    """RejectOrder command must emit exactly one order.rejected event."""
    db = OfficeDB(tmp_path / "test.db")
    fake_broker = FakeBracketBroker()
    office = build_test_office(db=db, broker=fake_broker, approval_mode="manual")

    draft = OrderDraft(
        symbol="AAPL",
        side="buy",
        quantity=Decimal("10"),
        entry=Decimal("150.0"),
        stop=Decimal("140.0"),
        take_profit=Decimal("170.0"),
        risk_reward=Decimal("2.0"),
        risk_amount=Decimal("100.0"),
        notional=Decimal("1500.0"),
    )
    ctx = RiskGateContext(
        equity=Decimal("100000"),
        cash=Decimal("50000"),
        positions={},
        sector_map={"AAPL": "technology"},
    )
    outcome = office.order_flow.process_accepted_order(
        ticker="AAPL",
        action="BUY",
        draft=draft,
        ctx=ctx,
        client_order_id="cid_r6_reject",
    )
    assert outcome.status == "pending"

    rt = Runtime(office=office)
    res = rt.execute(RejectOrder(order_id=outcome.order_id, reason="Valuation too high"), actor="test_user")
    assert res.ok is True

    rejected_events = [e for e in rt.event_log.since(0) if e.type == "order.rejected"]
    assert len(rejected_events) == 1
    assert rejected_events[0].payload.get("order_id") == outcome.order_id
    assert rejected_events[0].payload.get("reason") == "Valuation too high"
