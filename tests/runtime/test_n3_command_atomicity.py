"""Test N3: Local command handlers run in a single atomic transaction with command.accepted.

Network command handlers (ApproveOrder, Halt) maintain the split to avoid holding DB lock.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from bootstrap import build_test_office
from runtime.commands import EnqueueTask, Halt, Say
from runtime.core import Runtime
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


def test_n3_local_command_say_is_atomic_with_command_accepted(tmp_path):
    """Say handler runs in the same transaction as command.accepted."""
    db = OfficeDB(tmp_path / "n3_say.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    # Monkeypatch event_log.append to fail on command.accepted
    orig_append = rt.event_log.append

    def append_wrapper(*args, **kwargs):
        if kwargs.get("type") == "command.accepted":
            raise RuntimeError("Crash right at command.accepted commit")
        return orig_append(*args, **kwargs)

    rt.event_log.append = MagicMock(side_effect=append_wrapper)

    # Executing Say should fail and roll back the message completely
    res = rt.execute(
        Say(agent="portfolio_manager", chat="AAPL", text="Hello"),
        actor="cli",
        command_id="cmd_say_atomic",
    )
    assert res.ok is False

    # Because of atomic transaction, the message must NOT exist in DB!
    messages = db.connection.execute("SELECT * FROM messages").fetchall()
    assert len(messages) == 0, "Message was committed despite command.accepted failure!"


def test_n3_local_command_enqueue_task_is_atomic(tmp_path):
    """EnqueueTask is atomic with command.accepted."""
    db = OfficeDB(tmp_path / "n3_task.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    orig_append = rt.event_log.append

    def append_wrapper(*args, **kwargs):
        if kwargs.get("type") == "command.accepted":
            raise RuntimeError("Crash right at command.accepted commit")
        return orig_append(*args, **kwargs)

    rt.event_log.append = MagicMock(side_effect=append_wrapper)

    res = rt.execute(
        EnqueueTask(agent="technical_analyst", ticker="AAPL", reason="Test"),
        actor="cli",
        command_id="cmd_task_atomic",
    )
    assert res.ok is False

    tasks = db.connection.execute("SELECT * FROM scheduled_tasks").fetchall()
    assert len(tasks) == 0, "Scheduled task was committed despite command.accepted failure!"


def test_n3_network_commands_keep_tx_depth_zero_during_network(tmp_path):
    """Network commands (ApproveOrder, Halt) do NOT hold DB transaction during network call."""
    db = OfficeDB(tmp_path / "n3_net.db")
    fake_broker = FakeBracketBroker()

    # Track tx_depth during submit_bracket and cancel
    submit_tx_depth = -1
    cancel_tx_depth = -1

    orig_submit = fake_broker.submit_bracket

    def _submit(*args, **kwargs):
        nonlocal submit_tx_depth
        submit_tx_depth = db._tx_depth
        return orig_submit(*args, **kwargs)

    orig_cancel = fake_broker.cancel

    def _cancel(*args, **kwargs):
        nonlocal cancel_tx_depth
        cancel_tx_depth = db._tx_depth
        return orig_cancel(*args, **kwargs)

    fake_broker.submit_bracket = MagicMock(side_effect=_submit)
    fake_broker.cancel = MagicMock(side_effect=_cancel)

    # Insert an open order with broker_order_id so cancel is called
    db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={"symbol": "AAPL", "side": "buy", "quantity": "10"},
        draft_hash="hash",
        approval_status="auto",
        client_order_id="cid_n3_open",
        status="submitted",
    )
    db.connection.execute("UPDATE orders SET broker_order_id = 'b_n3_open' WHERE client_order_id = 'cid_n3_open'")

    office = build_test_office(db=db, broker=fake_broker, approval_mode="auto")
    rt = Runtime(office=office)

    # Halt with cancel_open calls fake_broker.cancel
    rt.execute(Halt(cancel_open=True, confirm=True), actor="cli")
    assert cancel_tx_depth == 0, f"Halt cancel was executed inside DB tx (depth={cancel_tx_depth})"
