"""Test N1: Reconciliation must not close open trades when position is present via SafeBrokerReader."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bootstrap import SafeBrokerReader, build_test_office
from brokers.models import Account, Position
from execution.trade_manager import TradeManager
from runtime.events import EventLog
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


def test_n1_safe_broker_reader_positions_do_not_close_open_trade(tmp_path):
    """SafeBrokerReader returns dicts with 'qty'.

    OrderFlow.sync_broker_orders must recognize them and keep the open Trade open!
    """
    db = OfficeDB(tmp_path / "n1.db")
    event_log = EventLog(db)
    fake_broker = FakeBracketBroker()

    # Create an open trade in DB
    order_id = db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={"symbol": "AAPL", "side": "buy", "quantity": "10"},
        draft_hash="hash",
        approval_status="auto",
        client_order_id="cid_open_trade_n1",
        status="filled",
    )
    db.update_order_status(order_id, status="filled", broker_order_id="b_open_n1")

    tm = TradeManager(db=db, broker=fake_broker, event_log=event_log)
    tm.record_entry_fill(order_id=order_id, fill_price=150.0, qty=10.0, ticker="AAPL")

    # Real production shape: SafeBrokerReader wrapping an inner reader
    acc = Account(
        id="test",
        status="ACTIVE",
        currency="USD",
        cash=Decimal("50000"),
        equity=Decimal("100000"),
        buying_power=Decimal("100000"),
        trading_blocked=False,
    )
    # Inner broker returns Position objects with 'quantity'
    pos = Position(
        symbol="AAPL",
        asset_class="us_equity",
        side="long",
        quantity=Decimal("10"),
        quantity_available=Decimal("10"),
        average_entry_price=Decimal("150.0"),
        current_price=Decimal("150.0"),
        market_value=Decimal("1500.0"),
        unrealized_profit_loss=Decimal("0"),
    )
    inner_reader = MagicMock()
    inner_reader.get_account.return_value = acc
    inner_reader.get_positions.return_value = (pos,)

    # Wrap in SafeBrokerReader -> returns [{'symbol': 'AAPL', 'qty': 10.0, ...}]
    safe_reader = SafeBrokerReader(inner_reader)
    positions_raw = safe_reader.get_positions()
    assert len(positions_raw) == 1
    assert "qty" in positions_raw[0]
    assert "quantity" not in positions_raw[0]  # Crucial: verify production shape!

    office = build_test_office(
        db=db,
        broker=fake_broker,
        broker_reader=safe_reader,
        event_log=event_log,
    )
    office.order_flow.trade_manager = tm

    # Run reconciliation
    office.order_flow.sync_broker_orders()

    # The open Trade MUST remain OPEN because AAPL position is open at broker!
    trade = db.connection.execute(
        "SELECT * FROM trades WHERE ticker = 'AAPL' AND closed_ts IS NULL"
    ).fetchone()
    assert trade is not None, "Trade was erroneously closed by reconciliation!"
    assert trade["closed_ts"] is None


def test_n1_reader_failure_does_not_touch_open_trades(tmp_path):
    """If broker reader fails (e.g. network/auth error), trades must NOT be closed."""
    db = OfficeDB(tmp_path / "n1_err.db")
    event_log = EventLog(db)
    fake_broker = FakeBracketBroker()

    order_id = db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={"symbol": "AAPL", "side": "buy", "quantity": "10"},
        draft_hash="hash",
        approval_status="auto",
        client_order_id="cid_open_trade_err",
        status="filled",
    )
    db.update_order_status(order_id, status="filled", broker_order_id="b_open_err")

    tm = TradeManager(db=db, broker=fake_broker, event_log=event_log)
    tm.record_entry_fill(order_id=order_id, fill_price=150.0, qty=10.0, ticker="AAPL")

    failing_reader = MagicMock()
    failing_reader.get_positions.side_effect = RuntimeError("Broker connection timeout")

    office = build_test_office(
        db=db,
        broker=fake_broker,
        broker_reader=failing_reader,
        event_log=event_log,
    )
    office.order_flow.trade_manager = tm

    # Run reconciliation: must not raise and must NOT close trade
    office.order_flow.sync_broker_orders()

    trade = db.connection.execute(
        "SELECT * FROM trades WHERE ticker = 'AAPL' AND closed_ts IS NULL"
    ).fetchone()
    assert trade is not None
    assert trade["closed_ts"] is None


def test_n1_closed_position_reconstructs_real_exit_fill_from_legs(tmp_path):
    """When position is closed at broker, reconciliation reconstructs exit fill from filled leg."""
    db = OfficeDB(tmp_path / "n1_legs.db")
    event_log = EventLog(db)
    fake_broker = FakeBracketBroker()

    order_id = db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={"symbol": "AAPL", "side": "buy", "quantity": "10"},
        draft_hash="hash",
        approval_status="auto",
        client_order_id="cid_open_trade_legs",
        status="filled",
    )
    db.update_order_status(order_id, status="filled", broker_order_id="b_parent_1")

    tm = TradeManager(db=db, broker=fake_broker, event_log=event_log)
    tm.record_entry_fill(order_id=order_id, fill_price=150.0, qty=10.0, ticker="AAPL")

    # Parent order has a filled take_profit leg at 175.0
    from types import SimpleNamespace

    from alpaca.trading.enums import OrderStatus, OrderType

    tp_leg = SimpleNamespace(
        status=OrderStatus.FILLED,
        order_type=OrderType.LIMIT,
        filled_avg_price="175.0",
        filled_at="2026-11-20T12:00:00Z",
    )

    parent_order = MagicMock()
    parent_order.legs = [tp_leg]
    fake_broker.get_order = MagicMock(return_value=parent_order)

    # Reader reports no positions (position closed!)
    reader = MagicMock()
    reader.get_positions.return_value = []

    office = build_test_office(
        db=db,
        broker=fake_broker,
        broker_reader=reader,
        event_log=event_log,
    )
    office.order_flow.trade_manager = tm

    office.order_flow.sync_broker_orders()

    trade = db.get_trade(1)
    assert trade["closed_ts"] is not None
    assert trade["exit_reason"] == "tp"
    assert trade["exit_price"] == 175.0


def test_n1_closed_position_without_fill_uses_reconciled_unknown_and_inbox(tmp_path):
    """When position closed but no fill is reconstructable, use reconciled_unknown and add inbox message."""
    db = OfficeDB(tmp_path / "n1_unknown.db")
    event_log = EventLog(db)
    fake_broker = FakeBracketBroker()

    order_id = db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={"symbol": "AAPL", "side": "buy", "quantity": "10"},
        draft_hash="hash",
        approval_status="auto",
        client_order_id="cid_open_trade_unk",
        status="filled",
    )
    db.update_order_status(order_id, status="filled", broker_order_id="b_parent_unk")

    tm = TradeManager(db=db, broker=fake_broker, event_log=event_log)
    tm.record_entry_fill(order_id=order_id, fill_price=150.0, qty=10.0, ticker="AAPL")

    fake_broker.get_order = MagicMock(return_value=None)
    reader = MagicMock()
    reader.get_positions.return_value = []
    reader.get_orders.return_value = []

    office = build_test_office(
        db=db,
        broker=fake_broker,
        broker_reader=reader,
        event_log=event_log,
    )
    office.order_flow.trade_manager = tm

    office.order_flow.sync_broker_orders()

    trade = db.get_trade(1)
    assert trade["closed_ts"] is not None
    assert trade["exit_reason"] == "reconciled_unknown"
    assert trade["exit_price"] is None

    # Check inbox message added
    inbox = db.list_inbox()
    assert any("reconciled_unknown" in item["text"] or "riconciliazione" in item["text"] for item in inbox)
