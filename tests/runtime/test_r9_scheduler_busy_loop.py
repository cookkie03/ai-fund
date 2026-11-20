"""Test R9: Scheduler avoids busy-loop when overdue tasks are filtered or cannot be delivered."""

from __future__ import annotations

from datetime import UTC, datetime

from bootstrap import build_test_office
from runtime.core import Runtime
from runtime.scheduler import Scheduler
from storage.office_db import OfficeDB
from tests.runtime.test_scheduler import FakeWaiter


def test_r9_scheduler_does_not_busy_loop_on_filtered_due_task(tmp_path):
    """When a task is due in DB but due_tasks cursor filters it out, scheduler does NOT sleep with timeout=0."""
    db = OfficeDB(tmp_path / "test.db")
    fake_waiter = FakeWaiter()
    office = build_test_office(db=db)

    # Insert a task that is due
    _ = db.enqueue_scheduled_task(
        agent="portfolio_manager",
        chat="AAPL",
        when_ts="2026-06-01T10:00:00Z",
        source="agent",
        reason="Test overdue task",
    )

    from workflows.scheduling import DueCursor

    # Pre-advance the office cursor past this task timestamp so due_tasks() drops it!
    office._cursor = DueCursor(last_delivered_when=datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC))

    rt = Runtime(office=office)
    clock_dt = datetime(2026, 6, 1, 10, 5, 0, tzinfo=UTC)
    scheduler = Scheduler(runtime=rt, clock=lambda: clock_dt, waiter=fake_waiter)

    # Step the scheduler
    scheduler.step()

    # The waiter should NOT have waited for 0.0s (busy loop)
    assert len(fake_waiter.wait_timeouts) == 1
    timeout = fake_waiter.wait_timeouts[0]
    # Timeout must either be None or a safe backoff (> 0.0), NOT 0.0
    assert timeout is None or timeout > 0.0
