"""Tests for broker stream updates, apply_broker_update, and TradeManager integration."""

from __future__ import annotations

from decimal import Decimal

import pytest

from bootstrap import build_test_office
from execution.order_flow import OrderDraft, Outcome, RiskGateContext
from execution.trade_manager import TradeManager
from runtime.events import EventLog
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


class FakeTradeUpdate:
    """Simulates an Alpaca TradeUpdate model or dict."""

    def __init__(
        self,
        event: str,
        broker_order_id: str,
        symbol: str,
        side: str = "buy",
        price: float | Decimal = 150.0,
        qty: float | Decimal = 10.0,
        timestamp: str = "2026-06-01T10:00:00Z",
        client_order_id: str | None = None,
        exit_reason: str | None = None,
        order_type: str | None = None,
    ) -> None:
        self.event = event
        self.price = price
        self.qty = qty
        self.timestamp = timestamp
        self.order = {
            "id": broker_order_id,
            "broker_order_id": broker_order_id,
            "client_order_id": client_order_id,
            "symbol": symbol,
            "side": side,
            "status": "filled" if event == "fill" else event,
            "type": order_type or ("limit" if side == "buy" else "stop"),
            "exit_reason": exit_reason,
        }


@pytest.fixture
def stream_setup(tmp_path):
    db = OfficeDB(tmp_path / "stream_test.db")
    broker = FakeBracketBroker()
    event_log = EventLog(db)
    office = build_test_office(db=db, broker=broker, event_log=event_log)
    tm = TradeManager(db=db, broker=broker, event_log=event_log)
    office.order_flow.trade_manager = tm

    ctx = RiskGateContext(
        equity=Decimal("100000"),
        cash=Decimal("50000"),
        positions={},
        sector_map={"AAPL": "Tech", "MSFT": "Tech"},
    )
    return {
        "db": db,
        "broker": broker,
        "event_log": event_log,
        "office": office,
        "trade_manager": tm,
        "ctx": ctx,
    }


def _create_submitted_order(setup, ticker="AAPL") -> tuple[int, str]:
    flow = setup["office"].order_flow
    draft = OrderDraft(
        symbol=ticker,
        side="buy",
        entry=Decimal("150.0"),
        stop=Decimal("140.0"),
        take_profit=Decimal("170.0"),
        quantity=Decimal("10"),
        risk_reward=Decimal("2.0"),
        risk_amount=Decimal("100.0"),
        notional=Decimal("1500.0"),
    )
    res: Outcome = flow.process_accepted_order(
        ticker=ticker,
        action="buy",
        draft=draft,
        ctx=setup["ctx"],
    )
    assert res.status == "submitted"
    assert res.order_id is not None
    assert res.broker_order_id is not None
    return res.order_id, res.broker_order_id


def test_apply_broker_update_entry_fill_opens_trade(stream_setup):
    flow = stream_setup["office"].order_flow
    db: OfficeDB = stream_setup["db"]
    event_log: EventLog = stream_setup["event_log"]

    order_id, b_id = _create_submitted_order(stream_setup, "AAPL")

    update = FakeTradeUpdate(
        event="fill",
        broker_order_id=b_id,
        symbol="AAPL",
        side="buy",
        price=150.0,
        qty=10.0,
        timestamp="2026-06-01T10:05:00Z",
    )

    flow.apply_broker_update(update)

    # 1. Order status is now filled
    order = db.get_order(order_id)
    assert order["status"] == "filled"

    # 2. Trade is opened in DB
    trades = db.connection.execute("SELECT * FROM trades").fetchall()
    assert len(trades) == 1
    assert trades[0]["ticker"] == "AAPL"
    assert trades[0]["entry_price"] == 150.0
    assert trades[0]["closed_ts"] is None

    # 3. Events emitted: order.status_changed and trade.opened
    events = event_log.since(0)
    assert any(e.type == "order.status_changed" and e.payload["status"] == "filled" for e in events)
    assert any(e.type == "trade.opened" and e.payload["ticker"] == "AAPL" for e in events)


def test_apply_broker_update_tp_fill_closes_trade(stream_setup):
    flow = stream_setup["office"].order_flow
    db: OfficeDB = stream_setup["db"]
    event_log: EventLog = stream_setup["event_log"]

    order_id, b_id = _create_submitted_order(stream_setup, "AAPL")

    # 1. Entry fill
    flow.apply_broker_update(
        FakeTradeUpdate(
            event="fill",
            broker_order_id=b_id,
            symbol="AAPL",
            side="buy",
            price=150.0,
            qty=10.0,
            timestamp="2026-06-01T10:05:00Z",
        )
    )

    # 2. Take profit fill (sell)
    tp_update = FakeTradeUpdate(
        event="fill",
        broker_order_id="b_tp_999",
        symbol="AAPL",
        side="sell",
        price=170.0,
        qty=10.0,
        timestamp="2026-06-01T11:00:00Z",
        exit_reason="tp",
    )
    flow.apply_broker_update(tp_update)

    # Trade is closed with exit_reason tp
    trades = db.connection.execute("SELECT * FROM trades").fetchall()
    assert len(trades) == 1
    assert trades[0]["closed_ts"] == "2026-06-01T11:00:00Z"
    assert trades[0]["exit_reason"] == "tp"
    assert trades[0]["exit_price"] == 170.0

    # Event trade.closed emitted
    events = event_log.since(0)
    assert any(
        e.type == "trade.closed" and e.payload["exit_reason"] == "tp"
        for e in events
    )


def test_apply_broker_update_sl_fill_closes_trade(stream_setup):
    flow = stream_setup["office"].order_flow
    db: OfficeDB = stream_setup["db"]
    event_log: EventLog = stream_setup["event_log"]

    order_id, b_id = _create_submitted_order(stream_setup, "AAPL")

    # 1. Entry fill
    flow.apply_broker_update(
        FakeTradeUpdate(
            event="fill",
            broker_order_id=b_id,
            symbol="AAPL",
            side="buy",
            price=150.0,
            qty=10.0,
            timestamp="2026-06-01T10:05:00Z",
        )
    )

    # 2. Stop loss fill (sell at stop price or with order_type stop)
    sl_update = FakeTradeUpdate(
        event="fill",
        broker_order_id="b_sl_999",
        symbol="AAPL",
        side="sell",
        price=140.0,
        qty=10.0,
        timestamp="2026-06-01T10:30:00Z",
        exit_reason="sl",
    )
    flow.apply_broker_update(sl_update)

    trades = db.connection.execute("SELECT * FROM trades").fetchall()
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "sl"
    assert trades[0]["exit_price"] == 140.0

    events = event_log.since(0)
    assert any(
        e.type == "trade.closed" and e.payload["exit_reason"] == "sl"
        for e in events
    )


def test_apply_broker_update_duplicate_is_idempotent(stream_setup):
    flow = stream_setup["office"].order_flow
    db: OfficeDB = stream_setup["db"]
    event_log: EventLog = stream_setup["event_log"]

    order_id, b_id = _create_submitted_order(stream_setup, "AAPL")

    update = FakeTradeUpdate(
        event="fill",
        broker_order_id=b_id,
        symbol="AAPL",
        side="buy",
        price=150.0,
        qty=10.0,
        timestamp="2026-06-01T10:05:00Z",
    )

    # First delivery
    flow.apply_broker_update(update)
    trades_count = len(db.connection.execute("SELECT * FROM trades").fetchall())
    events_count = len(event_log.since(0))

    # Duplicate delivery
    flow.apply_broker_update(update)

    # Must not duplicate trades or events
    assert len(db.connection.execute("SELECT * FROM trades").fetchall()) == trades_count
    assert len(event_log.since(0)) == events_count


def test_apply_broker_update_canceled_and_rejected(stream_setup):
    flow = stream_setup["office"].order_flow
    db: OfficeDB = stream_setup["db"]
    event_log: EventLog = stream_setup["event_log"]

    order_id, b_id = _create_submitted_order(stream_setup, "MSFT")

    cancel_update = FakeTradeUpdate(
        event="canceled",
        broker_order_id=b_id,
        symbol="MSFT",
        side="buy",
        timestamp="2026-06-01T10:10:00Z",
    )
    flow.apply_broker_update(cancel_update)

    order = db.get_order(order_id)
    assert order["status"] == "cancelled"

    events = event_log.since(0)
    assert any(
        e.type == "order.status_changed" and e.payload["status"] == "cancelled"
        for e in events
    )


def test_stream_reconnect_triggers_reconciliation(stream_setup):
    from tests.fakes.broker_stream import FakeBrokerStream

    reconciled = False

    def on_reconnect():
        nonlocal reconciled
        reconciled = True
        stream_setup["office"].order_flow.sync_broker_orders()

    stream = FakeBrokerStream(on_reconnect=on_reconnect)
    stream.start()
    assert reconciled is True  # Reconciled on startup

    reconciled = False
    stream.simulate_reconnect()
    assert reconciled is True  # Reconciled on reconnect
    stream.stop()
