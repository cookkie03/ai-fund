"""Periodic and scheduled jobs for the event-driven runtime scheduler."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.core import Runtime

logger = logging.getLogger(__name__)


class Job(ABC):
    """Abstract base class for scheduled recurring jobs."""

    name: str

    @abstractmethod
    def next_run(self, now: datetime) -> datetime | None:
        """Return the next datetime when this job should run, or None if not scheduled."""
        ...

    @abstractmethod
    def run(self, now: datetime) -> None:
        """Execute the job."""
        ...


class DataRefreshJob(Job):
    """Hourly market and portfolio data pre-fetch."""

    name = "data_refresh"

    def __init__(self, runtime: Runtime, interval_hours: float = 1.0) -> None:
        self.runtime = runtime
        self.interval = timedelta(hours=interval_hours)
        self.last_run: datetime | None = None

    def next_run(self, now: datetime) -> datetime | None:
        if self.last_run is None:
            return now
        return self.last_run + self.interval

    def run(self, now: datetime) -> None:
        self.last_run = now
        try:
            self.runtime.office.refresh_data(force=False)
        except Exception:
            logger.exception("Error executing DataRefreshJob")


class RetentionJob(Job):
    """Weekly DB retention cleanup and vacuum followed by size check."""

    name = "retention"

    def __init__(self, runtime: Runtime, interval_days: float = 7.0) -> None:
        self.runtime = runtime
        self.interval = timedelta(days=interval_days)
        self.last_run: datetime | None = None

    def next_run(self, now: datetime) -> datetime | None:
        if self.last_run is None:
            return now + self.interval
        return self.last_run + self.interval

    def run(self, now: datetime) -> None:
        self.last_run = now
        try:
            self.runtime.office.run_retention()
            self.runtime.office.check_db_size()
        except Exception:
            logger.exception("Error executing RetentionJob")


class MarketAnalystFixedJob(Job):
    """Fixed pre-market and macro event activations for Market Analyst."""

    name = "market_analyst_fixed"

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.last_run: datetime | None = None
        self.interval = timedelta(minutes=30)

    def next_run(self, now: datetime) -> datetime | None:
        if self.last_run is None:
            return now
        return self.last_run + self.interval

    def run(self, now: datetime) -> None:
        self.last_run = now
        try:
            self.runtime.office.ensure_fixed_market_analyst_activations()
        except Exception:
            logger.exception("Error executing MarketAnalystFixedJob")


class ExpirePendingOrdersJob(Job):
    """Expire pending orders at end of day / session."""

    name = "expire_pending"

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.interval = timedelta(minutes=15)
        self.last_run: datetime | None = None

    def next_run(self, now: datetime) -> datetime | None:
        if self.last_run is None:
            return now + self.interval
        return self.last_run + self.interval

    def run(self, now: datetime) -> None:
        self.last_run = now
        try:
            self.runtime.office.order_flow.expire_pending()
        except Exception:
            logger.exception("Error executing ExpirePendingOrdersJob")


class ReleaseQueuedOrdersJob(Job):
    """Release queued orders when market opens."""

    name = "release_queued"

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.interval = timedelta(minutes=5)
        self.last_run: datetime | None = None

    def next_run(self, now: datetime) -> datetime | None:
        if self.last_run is None:
            return now + self.interval
        return self.last_run + self.interval

    def run(self, now: datetime) -> None:
        self.last_run = now
        try:
            self.runtime.office.order_flow.release_queued()
        except Exception:
            logger.exception("Error executing ReleaseQueuedOrdersJob")
