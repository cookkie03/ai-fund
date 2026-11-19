from datetime import UTC, datetime, timedelta

import pytest

from bootstrap import build_test_office
from runtime.commands import EnqueueTask, Halt, Resume
from runtime.core import Runtime
from runtime.jobs import Job
from runtime.scheduler import Scheduler, Waiter
from storage.office_db import OfficeDB


class FakeWaiter(Waiter):
    """Fake waiter that does not block and records wait calls."""

    def __init__(self) -> None:
        self.wait_timeouts: list[float | None] = []
        self._is_set = False
        self.wake_count = 0

    def wait(self, timeout: float | None = None) -> bool:
        self.wait_timeouts.append(timeout)
        was_set = self._is_set
        self._is_set = False
        return was_set

    def wake(self) -> None:
        self.wake_count += 1
        self._is_set = True


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    def advance(self, td: timedelta) -> None:
        self.current += td


@pytest.fixture
def test_setup(tmp_path):
    db_path = tmp_path / "scheduler_test.db"
    db = OfficeDB(db_path)
    now = datetime(2026, 11, 20, 10, 0, 0, tzinfo=UTC)
    clock = FakeClock(now)
    waiter = FakeWaiter()
    office = build_test_office(db=db, clock=clock)
    rt = Runtime(office=office)
    scheduler = Scheduler(runtime=rt, clock=clock, waiter=waiter)
    return {
        "db": db,
        "runtime": rt,
        "clock": clock,
        "waiter": waiter,
        "scheduler": scheduler,
    }


def test_office_db_next_due_ts(test_setup):
    db: OfficeDB = test_setup["db"]
    assert db.next_due_ts() is None

    db.enqueue_scheduled_task(
        agent="market_analyst",
        chat="AAPL",
        when_ts="2026-11-20T11:00:00Z",
        source="manual",
        reason="test1",
    )
    db.enqueue_scheduled_task(
        agent="market_analyst",
        chat="MSFT",
        when_ts="2026-11-20T10:30:00Z",
        source="manual",
        reason="test2",
    )

    assert db.next_due_ts() == "2026-11-20T10:30:00Z"


def test_no_wake_without_tasks_or_jobs(test_setup):
    """When DB has no tasks and no jobs due, scheduler waits with timeout=None."""
    scheduler: Scheduler = test_setup["scheduler"]
    waiter: FakeWaiter = test_setup["waiter"]

    # Step one iteration of the scheduler loop
    scheduler.step()

    # With nothing due, waiter.wait was called with timeout=None
    assert len(waiter.wait_timeouts) == 1
    assert waiter.wait_timeouts[0] is None


def test_exact_wake_timeout_for_future_task(test_setup):
    """When a task is scheduled in the future, wait timeout is exactly (due - now)."""
    scheduler: Scheduler = test_setup["scheduler"]
    waiter: FakeWaiter = test_setup["waiter"]
    db: OfficeDB = test_setup["db"]

    # Now is 10:00:00, task is at 10:05:00 (300 seconds)
    db.enqueue_scheduled_task(
        agent="market_analyst",
        chat="AAPL",
        when_ts="2026-11-20T10:05:00Z",
        source="manual",
        reason="check",
    )

    scheduler.step()
    assert len(waiter.wait_timeouts) == 1
    assert pytest.approx(waiter.wait_timeouts[0], rel=1e-2) == 300.0


def test_enqueue_task_command_wakes_scheduler(test_setup):
    """Executing an EnqueueTask command immediately triggers scheduler.wake()."""
    rt: Runtime = test_setup["runtime"]
    waiter: FakeWaiter = test_setup["waiter"]
    scheduler: Scheduler = test_setup["scheduler"]

    scheduler.bind_events()
    prev_wakes = waiter.wake_count

    rt.execute(EnqueueTask(agent="market_analyst", ticker="AAPL", reason="Immediate wake"), actor="cli")

    assert waiter.wake_count > prev_wakes


def test_halt_blocks_until_resume(test_setup):
    """When halted, scheduler waits with None (no timeout) and does not deliver tasks."""
    scheduler: Scheduler = test_setup["scheduler"]
    waiter: FakeWaiter = test_setup["waiter"]
    rt: Runtime = test_setup["runtime"]
    db: OfficeDB = test_setup["db"]

    # Enqueue a task that is due right now
    db.enqueue_scheduled_task(
        agent="market_analyst",
        chat="AAPL",
        when_ts="2026-11-20T10:00:00Z",
        source="manual",
        reason="due now",
    )

    # Halt the system
    rt.execute(Halt(confirm=True), actor="cli")

    scheduler.step()

    # Because halted, it waited with None and did not process due tasks
    assert waiter.wait_timeouts[-1] is None
    tasks = rt.read.scheduled_tasks(status="pending")
    assert len(tasks) == 1  # Still pending!

    # Resume system
    rt.execute(Resume(confirm=True), actor="cli")
    scheduler.step()

    # Now it processed the due task
    tasks = rt.read.scheduled_tasks(status="pending")
    assert len(tasks) == 0


def test_job_runs_at_expiry(test_setup):
    """Job runs when now >= next_run, and scheduler computes wait timeout to its next_run."""
    scheduler: Scheduler = test_setup["scheduler"]
    clock: FakeClock = test_setup["clock"]
    waiter: FakeWaiter = test_setup["waiter"]

    job_run_count = 0

    class DummyJob(Job):
        name = "dummy"

        def next_run(self, now: datetime) -> datetime | None:
            # Due at 10:10:00
            return datetime(2026, 11, 20, 10, 10, 0, tzinfo=UTC)

        def run(self, now: datetime) -> None:
            nonlocal job_run_count
            job_run_count += 1

    scheduler.register_job(DummyJob())

    # At 10:00, next run is 10:10 (600s)
    scheduler.step()
    assert pytest.approx(waiter.wait_timeouts[-1], rel=1e-2) == 600.0
    assert job_run_count == 0

    # Advance clock past expiry
    clock.advance(timedelta(minutes=11))
    scheduler.step()
    assert job_run_count == 1


def test_task_retry_at_next_attempt_ts(test_setup):
    """When a task has next_attempt_ts in the future, wait timeout is calculated to next_attempt_ts."""
    scheduler: Scheduler = test_setup["scheduler"]
    waiter: FakeWaiter = test_setup["waiter"]
    db: OfficeDB = test_setup["db"]

    # Insert task with next_attempt_ts 120s in the future
    task_id = db.enqueue_scheduled_task(
        agent="market_analyst",
        chat="AAPL",
        when_ts="2026-11-20T10:00:00Z",
        source="manual",
        reason="retry test",
    )
    db.connection.execute(
        "UPDATE scheduled_tasks SET attempts = 1, next_attempt_ts = '2026-11-20T10:02:00Z' WHERE id = ?",
        (task_id,),
    )

    scheduler.step()
    assert len(waiter.wait_timeouts) == 1
    assert pytest.approx(waiter.wait_timeouts[0], rel=1e-2) == 120.0
