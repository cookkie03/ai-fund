import uuid

import pytest
from pydantic import ValidationError

from bootstrap import build_test_office
from runtime.commands import (
    AddWatchlist,
    ApproveOrder,
    EnqueueTask,
    Halt,
    IngestAlert,
    MarkInboxRead,
    ReconcileBroker,
    RefreshData,
    RejectOrder,
    RemoveWatchlist,
    Resume,
    Say,
)
from runtime.core import Runtime
from storage.office_db import OfficeDB


@pytest.fixture
def runtime(tmp_path):
    db_path = tmp_path / "office_test.db"
    db = OfficeDB(db_path)
    office = build_test_office(db=db)
    rt = Runtime(office=office)
    return rt


def test_command_enqueue_task(runtime: Runtime):
    cmd_id = str(uuid.uuid4())
    cmd = EnqueueTask(agent="market_analyst", ticker="AAPL", reason="Earnings review")
    res = runtime.execute(cmd, actor="cli", command_id=cmd_id)

    assert res.ok is True
    assert "task_id" in res.data

    # Read back via ReadModel
    tasks = runtime.read.scheduled_tasks(status="pending")
    assert any(t.chat == "AAPL" and t.agent == "market_analyst" for t in tasks)


def test_command_say_non_pm(runtime: Runtime):
    cmd = Say(agent="market_analyst", chat="MACRO", text="Inflation data release")
    res = runtime.execute(cmd, actor="cli", command_id=str(uuid.uuid4()))

    assert res.ok is True
    assert "message_id" in res.data
    assert "task_id" not in res.data

    # Verify message in chat
    messages = runtime.read.chat(agent="market_analyst", topic="MACRO")
    assert len(messages) == 1
    assert messages[0].text == "Inflation data release"


def test_command_say_to_pm_spawns_scheduled_task(runtime: Runtime):
    """Rule moved from CLI to handler: a message to PM enqueues a Scheduled task."""
    cmd = Say(agent="portfolio_manager", chat="MSFT", text="Review quarterly numbers")
    res = runtime.execute(cmd, actor="cli", command_id=str(uuid.uuid4()))

    assert res.ok is True
    assert "message_id" in res.data
    assert "task_id" in res.data

    # Check task was created
    tasks = runtime.read.scheduled_tasks(status="pending")
    pm_tasks = [t for t in tasks if t.agent == "portfolio_manager" and t.chat == "MSFT"]
    assert len(pm_tasks) == 1
    assert pm_tasks[0].reason == "Review quarterly numbers"


def test_command_watchlist_add_and_remove(runtime: Runtime):
    cmd_add = AddWatchlist(ticker="NVDA", note="AI leader")
    res_add = runtime.execute(cmd_add, actor="ui", command_id=str(uuid.uuid4()))
    assert res_add.ok is True

    items = runtime.read.watchlist()
    assert any(it.ticker == "NVDA" and it.note == "AI leader" for it in items)

    cmd_rem = RemoveWatchlist(ticker="NVDA")
    res_rem = runtime.execute(cmd_rem, actor="ui", command_id=str(uuid.uuid4()))
    assert res_rem.ok is True

    items_after = runtime.read.watchlist()
    assert not any(it.ticker == "NVDA" for it in items_after)


def test_command_approve_order_requires_confirm(runtime: Runtime):
    # Without confirm=True, Pydantic validation fails
    with pytest.raises(ValidationError):
        ApproveOrder(order_id=1, confirm=False)  # type: ignore[arg-type]


def test_command_approve_and_reject_order(runtime: Runtime):
    # Insert an order in pending approval
    order_id = runtime.office.db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={"qty": 10.0, "order_type": "bracket", "limit_price": 150.0, "stop_loss": 140.0, "take_profit": 170.0},
        draft_hash="hash123",
        approval_status="pending",
        client_order_id="c-test-01",
        status="pending_approval",
    )

    # Reject
    cmd_rej = RejectOrder(order_id=order_id, reason="Price too volatile")
    res_rej = runtime.execute(cmd_rej, actor="cli", command_id=str(uuid.uuid4()))
    assert res_rej.ok is True

    ord_detail = runtime.read.order(order_id)
    assert ord_detail is not None
    assert ord_detail.approval_status == "rejected"


def test_command_halt_and_resume(runtime: Runtime):
    cmd_halt = Halt(cancel_open=True, confirm=True)
    res_halt = runtime.execute(cmd_halt, actor="cli", command_id=str(uuid.uuid4()))
    assert res_halt.ok is True
    assert runtime.office.halt.is_halted() is True

    cmd_resume = Resume(confirm=True)
    res_resume = runtime.execute(cmd_resume, actor="cli", command_id=str(uuid.uuid4()))
    assert res_resume.ok is True
    assert runtime.office.halt.is_halted() is False


def test_command_reconcile_broker(runtime: Runtime):
    cmd = ReconcileBroker()
    res = runtime.execute(cmd, actor="cli", command_id=str(uuid.uuid4()))
    assert res.ok is True


def test_command_refresh_data(runtime: Runtime):
    cmd = RefreshData(kinds=["macro"], force=True)
    res = runtime.execute(cmd, actor="cli", command_id=str(uuid.uuid4()))
    assert res.ok is True


def test_command_inbox_mark_read(runtime: Runtime):
    item_id = runtime.office.db.add_inbox("alert", "Test inbox notification")
    unread = runtime.read.inbox(unread_only=True)
    assert any(it.id == item_id for it in unread)

    cmd = MarkInboxRead(item_id=item_id)
    res = runtime.execute(cmd, actor="cli", command_id=str(uuid.uuid4()))
    assert res.ok is True

    unread_after = runtime.read.inbox(unread_only=True)
    assert not any(it.id == item_id for it in unread_after)


def test_command_ingest_alert(runtime: Runtime):
    cmd = IngestAlert(
        ticker="TSLA",
        source="price",
        reason="Breakout above 250",
        data={"price": 251.0},
    )
    res = runtime.execute(cmd, actor="cli", command_id=str(uuid.uuid4()))
    assert res.ok is True


def test_command_idempotency_returns_saved_result(runtime: Runtime):
    cmd_id = "unique-cmd-12345"
    cmd = AddWatchlist(ticker="AMZN", note="First attempt")

    res1 = runtime.execute(cmd, actor="cli", command_id=cmd_id)
    assert res1.ok is True

    # Execute again with same command_id
    cmd2 = AddWatchlist(ticker="AMZN", note="Second attempt should not run")
    res2 = runtime.execute(cmd2, actor="cli", command_id=cmd_id)
    assert res2.ok is True
    assert res2.data == res1.data

    # Verify command.accepted event is recorded exactly once
    events = [e for e in runtime.event_log.since(0) if e.command_id == cmd_id]
    assert len(events) == 1
    assert events[0].type == "command.accepted"


def test_read_model_methods(runtime: Runtime):
    health = runtime.read.health()
    assert health.runtime_version == "0.1.0"
    assert health.halted is False

    # Portfolio is None initially
    assert runtime.read.portfolio() is None

    # Sync portfolio
    runtime.execute(ReconcileBroker(), actor="cli")
    portfolio = runtime.read.portfolio()
    assert portfolio is not None

    orders = runtime.read.orders()
    assert isinstance(orders, list)

    trades = runtime.read.trades()
    assert isinstance(trades, list)

    cycles = runtime.read.cycles()
    assert isinstance(cycles, list)
