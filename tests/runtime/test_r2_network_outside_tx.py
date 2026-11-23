"""Test R2: Broker network calls occur outside DB transactions; 2-phase order approval; async RefreshData."""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import MagicMock

from bootstrap import build_test_office
from execution.order_flow import OrderDraft, RiskGateContext
from runtime.commands import ApproveOrder, Halt, RefreshData
from runtime.core import Runtime
from storage.office_db import OfficeDB


def test_r2_approve_order_broker_call_outside_tx_and_persists_submitting(tmp_path):
    """When ApproveOrder is executed, broker.submit_bracket runs with tx_depth == 0.

    If the broker call fails, the order is NOT rolled back from DB: it retains
    its client_order_id in DB for reconciliation.
    """
    db = OfficeDB(tmp_path / "test.db")
    tx_depths_during_submit = []

    fake_broker = MagicMock()

    def _submit(*args, **kwargs):
        tx_depths_during_submit.append(db._tx_depth)
        raise RuntimeError("Network timeout talking to broker")

    fake_broker.submit_bracket.side_effect = _submit
    fake_broker.find_by_client_id.return_value = None

    from brokers.models import Account
    from tests.fakes.broker import EmptyBroker

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
        client_order_id="test_cid_r2",
    )
    assert outcome.status == "pending"
    order_id = outcome.order_id

    rt = Runtime(office=office)

    # Approve order via Runtime.execute
    _ = rt.execute(ApproveOrder(order_id=order_id, confirm=True), actor="test_user")

    # 1. Broker submit was called outside DB transaction (depth == 0)
    assert len(tx_depths_during_submit) == 1
    assert tx_depths_during_submit[0] == 0

    # 2. Even though broker failed, the order exists in DB with client_order_id
    saved = db.get_order(order_id)
    assert saved is not None
    assert saved["client_order_id"] == "test_cid_r2"
    # Status is reconcilable (submitting or rejected), not vanished
    assert saved["status"] in ("submitting", "rejected")


def test_r2_refresh_data_is_asynchronous(tmp_path):
    """RefreshData must return immediately (non-blocking) and produce data.refreshed event asynchronously."""
    db = OfficeDB(tmp_path / "test.db")
    office = build_test_office(db=db)

    def slow_refresh(*args, **kwargs):
        time.sleep(0.1)
        return {"prices": 5}

    office.refresh_data = slow_refresh
    rt = Runtime(office=office)

    t0 = time.monotonic()
    res = rt.execute(RefreshData(kinds=["prices"], force=True), actor="test_user")
    elapsed = time.monotonic() - t0

    assert res.ok is True
    # Returned immediately without waiting 0.1s
    assert elapsed < 0.08

    # Wait for background thread to emit event
    types = []
    for _ in range(20):
        events = list(rt.event_log.since(after_id=0))
        types = [e.type for e in events]
        if "data.refreshed" in types:
            break
        time.sleep(0.02)
        time.sleep(0.02)

    assert "data.refreshed" in types


def test_r2_halt_broker_call_outside_tx(tmp_path):
    """Halt broker cancel calls must run outside DB transaction (depth == 0)."""
    db = OfficeDB(tmp_path / "test.db")
    tx_depths_during_cancel = []

    fake_broker = MagicMock()

    def _cancel(*args, **kwargs):
        tx_depths_during_cancel.append(db._tx_depth)

    fake_broker.cancel.side_effect = _cancel

    office = build_test_office(db=db, broker=fake_broker)
    # Insert an open order
    order_id = db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={"symbol": "AAPL", "side": "buy", "quantity": "10"},
        draft_hash="hash",
        approval_status="approved",
        client_order_id="cid_halt",
        status="submitted",
    )
    db.update_order_status(order_id, status="submitted", broker_order_id="b_order_123")

    rt = Runtime(office=office)
    res = rt.execute(Halt(cancel_open=True, confirm=True), actor="test_user")
    assert res.ok is True

    assert len(tx_depths_during_cancel) == 1
    assert tx_depths_during_cancel[0] == 0
