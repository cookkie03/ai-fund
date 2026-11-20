"""Event-driven scheduler and trigger engine without polling."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.core import Runtime
    from runtime.events import Event
    from runtime.jobs import Job

logger = logging.getLogger(__name__)


class Waiter(ABC):
    """Abstract synchronization primitive for scheduler sleep/wake."""

    @abstractmethod
    def wait(self, timeout: float | None = None) -> bool:
        """Wait until woken or timeout expires. Return True if woken, False on timeout."""
        ...

    @abstractmethod
    def wake(self) -> None:
        """Wake up the waiting scheduler."""
        ...


class ThreadingWaiter(Waiter):
    """Production waiter backed by threading.Event."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def wait(self, timeout: float | None = None) -> bool:
        signaled = self._event.wait(timeout=timeout)
        self._event.clear()
        return signaled

    def wake(self) -> None:
        self._event.set()


class Scheduler:
    """Event-driven trigger engine that runs due tasks and scheduled jobs without busy polling."""

    def __init__(
        self,
        runtime: Runtime,
        clock: Callable[[], datetime] | None = None,
        waiter: Waiter | None = None,
        jobs: list[Job] | None = None,
    ) -> None:
        self.runtime = runtime
        self.clock = clock or (lambda: datetime.now(UTC))
        self.waiter = waiter or ThreadingWaiter()
        self.jobs: list[Job] = list(jobs) if jobs is not None else []
        self._stop_event = threading.Event()
        self._bound = False

    def register_job(self, job: Job) -> None:
        self.jobs.append(job)

    def bind_events(self) -> None:
        if self._bound:
            return
        self.runtime.bus.add_listener(self._on_bus_event)
        self._bound = True

    def _on_bus_event(self, event: Event) -> None:
        if event.type in (
            "task.enqueued",
            "task.failed",
            "task.merged",
            "order.created",
            "order.status_changed",
            "halt.changed",
            "runtime.stopped",
        ):
            self.wake()

    def wake(self) -> None:
        self.waiter.wake()

    def step(self) -> None:
        """Execute one iteration of the scheduler cycle."""
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        # 1. If system is halted: wait indefinitely until wake (halt.changed / stop)
        if self.runtime.office.halt.is_halted():
            self.waiter.wait(timeout=None)
            return

        # 2. Run due tasks in Office
        delivered = self.runtime.office.run_once()

        # 3. Run due jobs
        for job in self.jobs:
            next_run = job.next_run(now)
            if next_run is not None and next_run <= now:
                job.run(now)

        # 4. Compute next due time across DB scheduled_tasks and jobs
        earliest_due_dt: datetime | None = None
        next_due_iso = self.runtime.office.db.next_due_ts()
        if next_due_iso:
            try:
                dt = datetime.fromisoformat(next_due_iso.replace("Z", "+00:00"))
                earliest_due_dt = dt
            except Exception:
                pass

        now_after = self.clock()
        if now_after.tzinfo is None:
            now_after = now_after.replace(tzinfo=UTC)

        for job in self.jobs:
            nr = job.next_run(now_after)
            if nr is not None:
                if earliest_due_dt is None or nr < earliest_due_dt:
                    earliest_due_dt = nr

        # 5. Sleep until earliest due or event wake
        if earliest_due_dt is None:
            self.waiter.wait(timeout=None)
        else:
            diff = (earliest_due_dt - now_after).total_seconds()
            if diff <= 0:
                if not delivered:
                    # Overdue tasks exist but were not deliverable (e.g. filtered by cursor/limits).
                    # Avoid 0.0s busy-loop by applying a safe minimum backoff.
                    self.waiter.wait(timeout=1.0)
                else:
                    self.waiter.wait(timeout=0.0)
            else:
                self.waiter.wait(timeout=diff)

    def run(self) -> None:
        """Main scheduler loop."""
        self._stop_event.clear()
        self.bind_events()
        while not self._stop_event.is_set():
            try:
                self.step()
            except Exception:
                logger.exception("Error in scheduler loop")
                if not self._stop_event.is_set():
                    self.waiter.wait(timeout=1.0)

    def stop(self) -> None:
        """Stop the scheduler loop."""
        self._stop_event.set()
        self.wake()
