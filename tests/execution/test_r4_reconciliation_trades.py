"""Test R4: Broker reconciliation creates and closes Trades for offline fills."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bootstrap import build_test_office
from brokers.models import Account, Position
from execution.order_flow import OrderDraft, RiskGateContext
from execution.trade_manager import TradeManager
from runtime.events import EventLog
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


def _make_position(symbol: str, qty: Decimal, price: Decimal) -> Position:
    return Position(
        symbol=symbol,
        asset_class="us_equity",
        side="long",
        quantity=qty,
        quantity_available=qty,
        average_entry_price=price,
        current_price=price,
        market_value=qty * price,
        unrealized_profit_loss=Decimal("0"),
    )


def test_r4_reconciliation_creates_trade_for_offline_entry_fill(tmp_path):
    """When a submitted order fills while offline, reconciliation creates the Trade and emits events."""
    db = OfficeDB(tmp_path / "test.db")
    event_log = EventLog(db)
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
    pos = _make_position("AAPL", Decimal("10"), Decimal("150.0"))
    reader = MagicMock()
    reader.get_account.return_value = acc
    reader.get_positions.return_value = (pos,)

    office = build_test_office(
        db=db,
        broker=fake_broker,
        broker_reader=reader,
        event_log=event_log,
        approval_mode="auto",
    )
    # Submit a buy order
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
        client_order_id="cid_offline_entry",
    )
    assert outcome.status == "submitted"
    broker_order_id = outcome.broker_order_id

    # Simulate offline fill at broker while runtime is not running
    fake_broker.fill_order(broker_order_id, fill_price=150.0, fill_qty=10.0)

    # Reconcile via order_flow.sync_broker_orders()
    changed = office.order_flow.sync_broker_orders()
    assert outcome.order_id in changed

    # Order must now be filled
    order = db.get_order(outcome.order_id)
    assert order["status"] == "filled"

    # Trade must have been created!
    trade = db.connection.execute(
        "SELECT * FROM trades WHERE entry_order_id = ?", (outcome.order_id,)
    ).fetchone()
    assert trade is not None
    assert trade["ticker"] == "AAPL"
    assert trade["closed_ts"] is None

    # Events must include order.status_changed and trade.opened
    events = list(event_log.since(0))
    event_types = [e.type for e in events]
    assert "order.status_changed" in event_types
    assert "trade.opened" in event_types


def test_r4_reconciliation_closes_trade_for_offline_exit_fill(tmp_path):
    """When an open trade position is closed at the broker while offline, reconciliation closes the Trade."""
    db = OfficeDB(tmp_path / "test.db")
    event_log = EventLog(db)
    fake_broker = FakeBracketBroker()

    # Create an open trade in DB
    order_id = db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={"symbol": "AAPL", "side": "buy", "quantity": "10"},
        draft_hash="hash",
        approval_status="auto",
        client_order_id="cid_open_trade",
        status="filled",
    )
    db.update_order_status(order_id, status="filled", broker_order_id="b_open_1")

    tm = TradeManager(db=db, broker=fake_broker, event_log=event_log)
    tm.record_entry_fill(order_id=order_id, fill_price=150.0, qty=10.0, ticker="AAPL")

    trade_before = db.connection.execute(
        "SELECT * FROM trades WHERE ticker = 'AAPL' AND closed_ts IS NULL"
    ).fetchone()
    assert trade_before is not None

    # Broker reader now shows NO positions (position closed offline by TP/SL)
    acc = Account(
        id="test",
        status="ACTIVE",
        currency="USD",
        cash=Decimal("51700"),
        equity=Decimal("101700"),
        buying_power=Decimal("101700"),
        trading_blocked=False,
    )
    reader = MagicMock()
    reader.get_account.return_value = acc
    reader.get_positions.return_value = ()

    office = build_test_office(
        db=db,
        broker=fake_broker,
        broker_reader=reader,
        event_log=event_log,
    )
    office.order_flow.trade_manager = tm

    # Run reconciliation
    office.order_flow.sync_broker_orders()

    # Trade must now be closed!
    trade_after = db.connection.execute(
        "SELECT * FROM trades WHERE id = ?", (trade_before["id"],)
    ).fetchone()
    assert trade_after["closed_ts"] is not None

    # Event trade.closed must be emitted
    events = list(event_log.since(0))
    event_types = [e.type for e in events]
    assert "trade.closed" in event_types


def test_r4_reconciliation_is_idempotent(tmp_path):
    """Calling sync_broker_orders multiple times does not produce duplicate trades or events."""
    db = OfficeDB(tmp_path / "test.db")
    event_log = EventLog(db)
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
    pos = _make_position("MSFT", Decimal("5"), Decimal("400.0"))
    reader = MagicMock()
    reader.get_account.return_value = acc
    reader.get_positions.return_value = (pos,)

    office = build_test_office(
        db=db,
        broker=fake_broker,
        broker_reader=reader,
        event_log=event_log,
        approval_mode="auto",
    )
    draft = OrderDraft(
        symbol="MSFT",
        side="buy",
        quantity=Decimal("5"),
        entry=Decimal("400.0"),
        stop=Decimal("380.0"),
        take_profit=Decimal("440.0"),
        risk_reward=Decimal("2.0"),
        risk_amount=Decimal("100.0"),
        notional=Decimal("2000.0"),
    )
    ctx = RiskGateContext(
        equity=Decimal("100000"),
        cash=Decimal("50000"),
        positions={},
        sector_map={"MSFT": "technology"},
    )
    outcome = office.order_flow.process_accepted_order(
        ticker="MSFT",
        action="BUY",
        draft=draft,
        ctx=ctx,
        client_order_id="cid_msft_entry",
    )
    fake_broker.fill_order(outcome.broker_order_id, fill_price=400.0, fill_qty=5.0)

    # First reconciliation
    changed1 = office.order_flow.sync_broker_orders()
    assert outcome.order_id in changed1
    events1_count = len(list(event_log.since(0)))

    # Second reconciliation
    changed2 = office.order_flow.sync_broker_orders()
    assert len(changed2) == 0
    events2_count = len(list(event_log.since(0)))
    assert events2_count == events1_count
