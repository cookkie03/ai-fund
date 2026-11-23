"""Test R7: Fresh RiskGateContext evaluation upon order approval."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bootstrap import build_test_office
from brokers.models import Account, Position
from execution.order_flow import OrderDraft, RiskGateContext
from runtime.commands import ApproveOrder
from runtime.core import Runtime
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


def _make_pos(symbol: str) -> Position:
    return Position(
        symbol=symbol,
        asset_class="us_equity",
        side="long",
        quantity=Decimal("10"),
        quantity_available=Decimal("10"),
        average_entry_price=Decimal("100"),
        current_price=Decimal("100"),
        market_value=Decimal("1000"),
        unrealized_profit_loss=Decimal("0"),
    )


def test_r7_approve_order_reruns_risk_gate_and_blocks_if_portfolio_limits_violated(tmp_path):
    """If portfolio conditions worsen before approval (e.g. cash depleted), approval must be rejected by Risk Gate."""
    db = OfficeDB(tmp_path / "test.db")
    fake_broker = FakeBracketBroker()

    # Initial good account
    acc = Account(
        id="test",
        status="ACTIVE",
        currency="USD",
        cash=Decimal("50000"),
        equity=Decimal("100000"),
        buying_power=Decimal("100000"),
        trading_blocked=False,
    )
    reader = MagicMock()
    reader.get_account.return_value = acc
    reader.get_positions.return_value = ()

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
        client_order_id="cid_r7_test",
    )
    assert outcome.status == "pending"

    # Worsen account: cash is now 0 (below minimum cash reserve of 5% equity)
    acc_depleted = Account(
        id="test",
        status="ACTIVE",
        currency="USD",
        cash=Decimal("0"),
        equity=Decimal("100000"),
        buying_power=Decimal("0"),
        trading_blocked=False,
    )
    reader.get_account.return_value = acc_depleted

    rt = Runtime(office=office)
    res = rt.execute(ApproveOrder(order_id=outcome.order_id, confirm=True), actor="test_user")

    # Must be rejected / blocked by Risk Gate
    assert res.ok is False
    assert any("cash reserve" in r.lower() for r in res.reasons)

    # Order must not have been submitted to broker
    assert fake_broker.find_by_client_id("cid_r7_test") is None
    saved = db.get_order(outcome.order_id)
    assert saved["approval_status"] == "rejected"
