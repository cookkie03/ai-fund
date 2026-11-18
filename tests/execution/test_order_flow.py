"""Tests for OrderFlow: Risk Gate, approval queue, serialized submission, idempotency, halt."""

from __future__ import annotations

from decimal import Decimal

import pytest

from execution.order_draft import OrderDraft, OrderDraftInputs, build_order_draft
from execution.order_flow import BracketBroker, OrderFlow, Outcome, SystemHalt
from execution.risk_gate import RiskGateContext, RiskGateLimits
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


@pytest.fixture
def db(tmp_path) -> OfficeDB:
    return OfficeDB(tmp_path / "office_test.db")


@pytest.fixture
def broker() -> FakeBracketBroker:
    return FakeBracketBroker()


@pytest.fixture
def valid_buy_draft() -> OrderDraft:
    inputs = OrderDraftInputs(
        symbol="AAPL",
        side="buy",
        current_price=Decimal("50.0"),
        atr=Decimal("3.0"),
        equity=Decimal("100000.0"),
        risk_fraction=Decimal("0.01"),
        k_entry=Decimal("0.5"),
        k_stop=Decimal("2.0"),
        k_tp=Decimal("3.0"),
    )
    return build_order_draft(inputs)


@pytest.fixture
def valid_gate_ctx() -> RiskGateContext:
    return RiskGateContext(
        equity=Decimal("100000.0"),
        cash=Decimal("50000.0"),
        positions={},
        sector_map={"AAPL": "Technology"},
        open_positions_count=0,
        limits=RiskGateLimits(),
    )


def test_bracket_broker_protocol_compliance(broker):
    """Verify FakeBracketBroker satisfies BracketBroker Protocol."""
    assert isinstance(broker, BracketBroker)


def test_order_flow_auto_approval_submits_bracket(db, broker, valid_buy_draft, valid_gate_ctx):
    """Stories 57, 63: Mode 'auto' immediately submits bracket order with limit, TP, SL."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="auto")

    outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )

    assert outcome.is_submitted
    assert outcome.status == "submitted"
    assert outcome.broker_order_id is not None
    assert outcome.order_id is not None

    # Check broker received the bracket
    broker_order = broker.get_order(outcome.broker_order_id)
    assert broker_order is not None
    assert broker_order.symbol == "AAPL"
    assert broker_order.side == "buy"
    assert broker_order.limit_price == valid_buy_draft.limit_price
    assert broker_order.take_profit == valid_buy_draft.take_profit
    assert broker_order.stop_loss == valid_buy_draft.stop

    # Check DB orders record
    db_order = db.get_order(outcome.order_id)
    assert db_order["status"] == "submitted"
    assert db_order["approval_status"] == "auto"
    assert db_order["broker_order_id"] == outcome.broker_order_id

    # Check order events
    events = db.list_order_events(outcome.order_id)
    event_names = [e["event"] for e in events]
    assert "created" in event_names
    assert "submitted" in event_names


def test_risk_gate_blocks_order_becomes_deferral(db, broker, valid_buy_draft):
    """Stories 53-55: Risk Gate blocking returns Outcome deferred with reasons."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="auto")

    # Insufficient cash violates cash reserve guard
    low_cash_ctx = RiskGateContext(
        equity=Decimal("100000.0"),
        cash=Decimal("1000.0"),  # Less than min 5% reserve after buying
        positions={},
        sector_map={"AAPL": "Technology"},
        open_positions_count=0,
    )

    outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=low_cash_ctx
    )

    assert outcome.is_deferred
    assert outcome.status == "deferred"
    assert len(outcome.reasons) > 0
    assert any("Cash after order" in r for r in outcome.reasons)
    # Broker should not receive any order
    assert len(broker.orders) == 0


def test_order_flow_manual_approval_queue(db, broker, valid_buy_draft, valid_gate_ctx):
    """Stories 56, 58, 59, 60: Manual approval queue binds draft hash and re-runs Risk Gate."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="manual")

    outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )

    assert outcome.is_pending
    assert outcome.status == "pending"
    order_id = outcome.order_id
    assert order_id is not None
    assert len(broker.orders) == 0

    order_in_db = db.get_order(order_id)
    assert order_in_db["approval_status"] == "pending"
    assert order_in_db["draft_hash"] == valid_buy_draft.draft_hash

    # Approve with matching draft
    approved_outcome = flow.approve(
        order_id=order_id, current_draft=valid_buy_draft, ctx=valid_gate_ctx
    )
    assert approved_outcome.is_submitted
    assert len(broker.orders) == 1

    # Order in DB is now approved and submitted
    updated_order = db.get_order(order_id)
    assert updated_order["approval_status"] == "approved"
    assert updated_order["status"] == "submitted"


def test_manual_approval_fails_if_draft_hash_changed(db, broker, valid_buy_draft, valid_gate_ctx):
    """Story 59: Approval fails if the draft hash changed."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="manual")

    outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )
    order_id = outcome.order_id

    # Create modified draft with different k_tp
    modified_inputs = OrderDraftInputs(
        symbol="AAPL",
        side="buy",
        current_price=Decimal("50.0"),
        atr=Decimal("3.0"),
        equity=Decimal("100000.0"),
        risk_fraction=Decimal("0.01"),
        k_entry=Decimal("0.5"),
        k_stop=Decimal("2.0"),
        k_tp=Decimal("4.0"),  # Changed
    )
    modified_draft = build_order_draft(modified_inputs)
    assert modified_draft.draft_hash != valid_buy_draft.draft_hash

    appr_outcome = flow.approve(
        order_id=order_id, current_draft=modified_draft, ctx=valid_gate_ctx
    )
    assert appr_outcome.is_deferred
    assert "Draft hash changed" in appr_outcome.reasons
    assert len(broker.orders) == 0

    # DB order is rejected
    db_order = db.get_order(order_id)
    assert db_order["approval_status"] == "rejected"


def test_manual_approval_reruns_risk_gate_with_fresh_portfolio(
    db, broker, valid_buy_draft, valid_gate_ctx
):
    """Story 60: Risk gate is re-run at approval time with fresh portfolio context."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="manual")

    outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )
    order_id = outcome.order_id

    # In the meantime, portfolio changed: max open positions reached
    stale_ctx = RiskGateContext(
        equity=Decimal("100000.0"),
        cash=Decimal("50000.0"),
        positions={},
        sector_map={"AAPL": "Technology"},
        open_positions_count=30,  # Max allowed is 30
        limits=RiskGateLimits(max_open_positions=30),
    )

    appr_outcome = flow.approve(order_id=order_id, current_draft=valid_buy_draft, ctx=stale_ctx)
    assert appr_outcome.is_deferred
    assert any("Max open positions reached" in r for r in appr_outcome.reasons)
    assert len(broker.orders) == 0


def test_reject_order(db, broker, valid_buy_draft, valid_gate_ctx):
    """Story 62: User rejection records reason and marks order rejected/deferred."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="manual")

    outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )
    order_id = outcome.order_id

    reject_outcome = flow.reject(order_id, reason="Too volatile")
    assert reject_outcome.is_deferred
    assert "Too volatile" in reject_outcome.reasons

    db_order = db.get_order(order_id)
    assert db_order["approval_status"] == "rejected"

    events = db.list_order_events(order_id)
    assert any(e["event"] == "rejected" for e in events)


def test_expire_pending_at_end_of_session(db, broker, valid_buy_draft, valid_gate_ctx):
    """Stories 61, 117: Pending orders expire at end of session and add inbox entry."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="manual")

    outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )
    order_id = outcome.order_id

    expired = flow.expire_pending(now="2026-11-18T16:00:00Z")
    assert order_id in expired

    db_order = db.get_order(order_id)
    assert db_order["approval_status"] == "expired"
    assert db_order["status"] == "expired"

    # Inbox entry created
    inbox_items = db.list_inbox()
    assert any(
        item["kind"] == "order_expired" and "AAPL" in item["text"] for item in inbox_items
    )


def test_idempotency_with_client_order_id(db, broker, valid_buy_draft, valid_gate_ctx):
    """Story 67: If client_order_id already exists on broker, reconcile without duplicate submit."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="auto")

    cid = "test-cid-aapl-001"
    # Pre-populate order on broker
    existing_broker_id = broker.submit_bracket(
        client_order_id=cid,
        symbol="AAPL",
        side="buy",
        qty=Decimal("10"),
        limit_price=Decimal("148.0"),
        take_profit=Decimal("155.0"),
        stop_loss=Decimal("142.0"),
    )

    initial_orders_count = len(broker.orders)

    outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx, client_order_id=cid
    )

    assert outcome.is_submitted
    assert outcome.broker_order_id == existing_broker_id
    # No new order created on broker
    assert len(broker.orders) == initial_orders_count

    # Check reconciled event in DB
    events = db.list_order_events(outcome.order_id)
    assert any(e["event"] == "reconciled" for e in events)


def test_market_closed_queues_order_and_releases_when_open(
    db, broker, valid_buy_draft, valid_gate_ctx
):
    """Story 65: Orders submitted when market is closed are queued until open."""
    broker.market_open = False
    flow = OrderFlow(db=db, broker=broker, approval_mode="auto")

    outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )

    assert outcome.is_queued
    assert outcome.status == "queued"
    assert len(broker.orders) == 0

    db_order = db.get_order(outcome.order_id)
    assert db_order["status"] == "queued"

    # Market opens -> release queued orders
    broker.market_open = True
    released = flow.release_queued()

    assert len(released) == 1
    assert released[0].is_submitted
    assert len(broker.orders) == 1

    updated_order = db.get_order(outcome.order_id)
    assert updated_order["status"] == "submitted"


def test_system_halt_blocks_orders_and_cancels_open(db, broker, valid_buy_draft, valid_gate_ctx):
    """Stories 114-116: Halt blocks order sending and cancels open orders."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="auto")

    # First submit an order while open
    outcome1 = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )
    assert outcome1.is_submitted
    b_id = outcome1.broker_order_id

    # Halt the system
    flow.halt(cancel_open=True)

    halt_obj = SystemHalt(db, broker)
    assert halt_obj.is_halted()

    # Verify previous open order was cancelled on broker and DB
    assert b_id in broker.cancelled_orders
    order_in_db = db.get_order(outcome1.order_id)
    assert order_in_db["status"] == "cancelled"

    # Inbox entry for halt
    inbox_items = db.list_inbox()
    assert any(item["kind"] == "halt" for item in inbox_items)

    # New order during halt is blocked
    outcome2 = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )
    assert outcome2.is_deferred
    assert any("halted" in r.lower() for r in outcome2.reasons)

    # Resume trading
    flow.resume()
    assert not halt_obj.is_halted()

    outcome3 = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )
    assert outcome3.is_submitted


def test_sell_on_open_position_moves_tp(db, broker, valid_buy_draft, valid_gate_ctx):
    """Stories 68, 69: Sell on an open position moves the TP of the open bracket to sell limit price."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="auto")

    # 1. Buy order executes
    buy_outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )
    broker_order_id = buy_outcome.broker_order_id

    # 2. Sell draft on open position
    sell_inputs = OrderDraftInputs(
        symbol="AAPL",
        side="sell",
        current_price=Decimal("55.0"),
        atr=Decimal("3.0"),
        equity=Decimal("100000.0"),
        risk_fraction=Decimal("0.01"),
        k_entry=Decimal("0.5"),
        position_quantity=valid_buy_draft.quantity,
    )
    sell_draft = build_order_draft(sell_inputs)

    # Context with held position
    sell_gate_ctx = RiskGateContext(
        equity=Decimal("100000.0"),
        cash=Decimal("50000.0"),
        positions={"AAPL": Decimal("8051.0")},
        position_quantities={"AAPL": valid_buy_draft.quantity},
        sector_map={"AAPL": "Technology"},
        open_positions_count=1,
    )

    sell_outcome = flow.process_accepted_order(
        ticker="AAPL", action="sell", draft=sell_draft, ctx=sell_gate_ctx
    )

    assert sell_outcome.is_submitted
    assert sell_outcome.broker_order_id == broker_order_id

    # Broker TP was modified to sell limit price
    assert len(broker.modified_take_profits) == 1
    mod_id, new_tp = broker.modified_take_profits[0]
    assert mod_id == broker_order_id
    assert new_tp == sell_draft.limit_price


def test_cancel_entry_if_unfilled(db, broker, valid_buy_draft, valid_gate_ctx):
    """Stories 64, 117: Entry order expires at the next scheduled task if unfilled."""
    flow = OrderFlow(db=db, broker=broker, approval_mode="auto")

    outcome = flow.process_accepted_order(
        ticker="AAPL", action="accept", draft=valid_buy_draft, ctx=valid_gate_ctx
    )
    b_id = outcome.broker_order_id

    # Broker order remains unfilled
    assert broker.get_order(b_id).filled_quantity == Decimal("0")

    cancelled = flow.cancel_entry_if_unfilled("AAPL")
    assert cancelled is True

    # Broker order cancelled
    assert b_id in broker.cancelled_orders

    # DB order status expired
    db_order = db.get_order(outcome.order_id)
    assert db_order["status"] == "expired"

    # Inbox notification recorded
    inbox_items = db.list_inbox()
    assert any(
        item["kind"] == "order_expired" and "AAPL" in item["text"] for item in inbox_items
    )
