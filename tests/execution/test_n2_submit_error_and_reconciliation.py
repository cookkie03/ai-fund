"""Test N2: Distinction between network timeout (submitting) and explicit broker rejection (rejected)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bootstrap import build_test_office
from brokers.models import BrokerError
from execution.order_flow import OrderDraft, RiskGateContext
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


def _make_ctx() -> RiskGateContext:
    return RiskGateContext(
        equity=Decimal("100000"),
        cash=Decimal("50000"),
        positions={},
        sector_map={"AAPL": "technology"},
    )


def _make_draft() -> OrderDraft:
    return OrderDraft(
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


def test_n2_network_timeout_found_immediately_by_client_id(tmp_path):
    """If submit_bracket times out but find_by_client_id finds it immediately, order is submitted."""
    db = OfficeDB(tmp_path / "n2_found.db")
    fake_broker = FakeBracketBroker()

    # submit_bracket saves order in fake broker then raises TimeoutError
    orig_submit = fake_broker.submit_bracket

    def _submit_with_timeout(**kwargs):
        orig_submit(**kwargs)
        raise TimeoutError("Gateway timeout on response")

    fake_broker.submit_bracket = MagicMock(side_effect=_submit_with_timeout)

    office = build_test_office(db=db, broker=fake_broker, approval_mode="auto")
    outcome = office.order_flow.process_accepted_order(
        ticker="AAPL",
        action="BUY",
        draft=_make_draft(),
        ctx=_make_ctx(),
        client_order_id="cid_n2_immediate",
    )

    # find_by_client_id found the order immediately!
    assert outcome.status == "submitted"
    assert outcome.broker_order_id == fake_broker.client_map["cid_n2_immediate"]
    saved = db.get_order(outcome.order_id)
    assert saved["status"] == "submitted"
    assert saved["broker_order_id"] == fake_broker.client_map["cid_n2_immediate"]


def test_n2_network_timeout_broker_unreachable_stays_submitting_then_reconciled(tmp_path):
    """If submit_bracket times out and broker is unreachable, order stays submitting until sync."""
    db = OfficeDB(tmp_path / "n2_unreachable.db")
    fake_broker = FakeBracketBroker()

    # Pre-populate broker order as if broker created it before disconnect
    fake_broker.client_map["cid_n2_reconcile"] = "b_n2_reconcile"
    fake_broker.orders["b_n2_reconcile"] = MagicMock(
        broker_order_id="b_n2_reconcile",
        id="b_n2_reconcile",
        status="submitted",
        symbol="AAPL",
        side="buy",
    )

    # During submit: submit raises Timeout AND find_by_client_id fails with ConnectionError
    fake_broker.submit_bracket = MagicMock(side_effect=TimeoutError("Timeout"))
    fake_broker.find_by_client_id = MagicMock(side_effect=ConnectionError("Broker offline"))

    office = build_test_office(db=db, broker=fake_broker, approval_mode="auto")
    outcome = office.order_flow.process_accepted_order(
        ticker="AAPL",
        action="BUY",
        draft=_make_draft(),
        ctx=_make_ctx(),
        client_order_id="cid_n2_reconcile",
    )

    # Stays submitting!
    assert outcome.status == "submitting"
    saved = db.get_order(outcome.order_id)
    assert saved["status"] == "submitting"
    assert saved["broker_order_id"] is None

    # Now broker comes back online: restore find_by_client_id
    fake_broker.find_by_client_id = MagicMock(return_value=fake_broker.orders["b_n2_reconcile"])
    fake_broker.get_order = MagicMock(return_value=fake_broker.orders["b_n2_reconcile"])

    # Reconciliation runs
    office.order_flow.sync_broker_orders()

    saved_after = db.get_order(outcome.order_id)
    assert saved_after["status"] == "submitted"
    assert saved_after["broker_order_id"] == "b_n2_reconcile"


def test_n2_explicit_broker_rejection_marks_rejected(tmp_path):
    """If broker explicitly rejects order (4xx / BrokerError), order is marked rejected."""
    db = OfficeDB(tmp_path / "n2_rejection.db")
    fake_broker = FakeBracketBroker()

    # Explicit 422 BrokerError
    fake_broker.submit_bracket = MagicMock(
        side_effect=BrokerError("invalid_order", status_code=422)
    )

    office = build_test_office(db=db, broker=fake_broker, approval_mode="auto")
    outcome = office.order_flow.process_accepted_order(
        ticker="AAPL",
        action="BUY",
        draft=_make_draft(),
        ctx=_make_ctx(),
        client_order_id="cid_n2_reject",
    )

    assert outcome.status == "rejected"
    saved = db.get_order(outcome.order_id)
    assert saved["status"] == "rejected"
