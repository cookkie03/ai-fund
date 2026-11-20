"""Final verification smoke test for review R1-R12 requirements."""

from __future__ import annotations

import io
from decimal import Decimal
from unittest.mock import MagicMock

from bootstrap import build_test_office
from brokers.models import Account, Position
from execution.order_flow import OrderDraft, RiskGateContext
from interface.cli import main
from runtime.commands import ApproveOrder, Halt
from runtime.core import Runtime
from runtime.http import create_app
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker
from tests.fakes.broker import EmptyBroker


def test_smoke_single_halt_event_per_command(tmp_path):
    """Smoke: un solo halt.changed per comando."""
    db = OfficeDB(tmp_path / "smoke_halt.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    rt.execute(Halt(cancel_open=False, confirm=True), actor="cli")
    halt_events = [e for e in rt.event_log.since(0) if e.type == "halt.changed"]
    assert len(halt_events) == 1


def test_smoke_second_runtime_refused_before_touching_db(tmp_path, monkeypatch):
    """Smoke: secondo Runtime rifiutato prima di toccare il DB."""
    import fcntl

    db_path = tmp_path / "smoke_colliding.db"
    lock_path = db_path.with_suffix(".db.lock")

    lock_file = open(lock_path, "w")
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    monkeypatch.setenv("TRADING_AGENT_DB", str(db_path))

    office_built = False

    def _factory():
        nonlocal office_built
        office_built = True
        return MagicMock()

    out = io.StringIO()
    try:
        code = main(["run"], out=out, runtime_factory=_factory)
        assert code != 0
        assert office_built is False
        assert "già attivo" in out.getvalue() or "already running" in out.getvalue().lower()
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def test_smoke_sse_after_no_holes_during_concurrent_commands(tmp_path):
    """Smoke: SSE con ?after= senza buchi durante comandi concorrenti."""
    db = OfficeDB(tmp_path / "smoke_sse.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    from starlette.testclient import TestClient

    app = create_app(runtime=rt, host="127.0.0.1")
    client = TestClient(app)

    # Invia alcuni eventi iniziali
    for i in range(1, 4):
        rt.event_log.append(type="seed.event", subject="test", payload={"i": i}, actor="test")

    with client.stream("GET", "/v1/events?after=0") as response:
        # Invia un evento mentre lo stream è aperto
        rt.event_log.append(type="live.event", subject="test", payload={"live": True}, actor="test")

        received_lines = []
        for line in response.iter_lines():
            if line:
                received_lines.append(line)
            if any(item.startswith("event: live.event") for item in received_lines):
                break

    ids = [int(line_item.split(": ")[1]) for line_item in received_lines if line_item.startswith("id: ")]
    # Nessun buco negli ID degli eventi
    assert ids == [1, 2, 3, 4]


def test_smoke_offline_fill_then_start_opens_trade(tmp_path):
    """Smoke: fill a Runtime spento, poi avvio => Trade aperto correttamente."""
    db = OfficeDB(tmp_path / "smoke_offline.db")
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
    reader = MagicMock()
    reader.get_account.return_value = acc
    reader.get_positions.return_value = (pos,)

    office = build_test_office(
        db=db,
        broker=fake_broker,
        broker_reader=reader,
        approval_mode="auto",
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
    outcome = office.order_flow.process_accepted_order("AAPL", "BUY", draft, ctx, "cid_smoke")
    assert outcome.status == "submitted"

    # Fill mentre Runtime è spento
    fake_broker.fill_order(outcome.broker_order_id, fill_price=150.0, fill_qty=10.0)

    # Avvio Runtime -> deve riconciliare ed aprire il Trade
    rt = Runtime(office=office)
    rt.start()
    try:
        trade = db.connection.execute(
            "SELECT * FROM trades WHERE entry_order_id = ?", (outcome.order_id,)
        ).fetchone()
        assert trade is not None
        assert trade["ticker"] == "AAPL"
        assert trade["closed_ts"] is None
    finally:
        rt.stop()


def test_smoke_submit_fails_order_reconcilable_not_lost(tmp_path):
    """Smoke: submit con errore broker => ordine riconciliabile, non perso da rollback."""
    db = OfficeDB(tmp_path / "smoke_submit_err.db")
    fake_broker = FakeBracketBroker()
    submit = fake_broker.submit_bracket

    def accepted_then_timeout(**kwargs):
        submit(**kwargs)
        raise TimeoutError("Broker gateway timeout")

    fake_broker.submit_bracket = MagicMock(side_effect=accepted_then_timeout)

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
    outcome = office.order_flow.process_accepted_order("AAPL", "BUY", draft, ctx, "cid_reconcilable")
    assert outcome.status == "pending"

    rt = Runtime(office=office)
    res = rt.execute(ApproveOrder(order_id=outcome.order_id, confirm=True), actor="cli")
    assert res.ok is False

    # L'ordine è rimasto nel DB con il suo client_order_id
    saved = db.get_order(outcome.order_id)
    assert saved is not None
    assert saved["client_order_id"] == "cid_reconcilable"
    assert saved["status"] == "submitting"
    office.order_flow.sync_broker_orders()
    saved = db.get_order(outcome.order_id)
    assert saved["status"] == "submitted"
    assert saved["broker_order_id"] == fake_broker.client_map["cid_reconcilable"]
    office.order_flow.sync_broker_orders()
    assert len(fake_broker.orders) == 1
