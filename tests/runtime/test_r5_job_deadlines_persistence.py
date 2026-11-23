"""Test R5: Jobs calculate exact deadlines (not fixed periodic intervals) and persist run history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from bootstrap import build_test_office
from runtime.core import Runtime
from runtime.jobs import (
    DataRefreshJob,
    ExpirePendingOrdersJob,
    ReleaseQueuedOrdersJob,
    RetentionJob,
)
from storage.office_db import OfficeDB
from tests.fakes.bracket_broker import FakeBracketBroker


def test_r5_job_run_persistence_across_runtime_restart(tmp_path):
    """Job run timestamps are persisted via event log and survive Runtime restart."""
    db = OfficeDB(tmp_path / "test.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    now = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)

    # 1. Run DataRefreshJob and RetentionJob
    refresh_job = DataRefreshJob(rt, interval_hours=1.0)
    retention_job = RetentionJob(rt, interval_days=7.0)

    refresh_job.run(now)
    retention_job.run(now)

    # Verify job.ran events in DB
    events = list(rt.event_log.since(0))
    job_events = [e for e in events if e.type == "job.ran"]
    assert len(job_events) >= 2

    # 2. Simulate process restart with fresh Runtime instance on same DB
    rt2 = Runtime(office=office)
    refresh_job2 = DataRefreshJob(rt2, interval_hours=1.0)
    retention_job2 = RetentionJob(rt2, interval_days=7.0)

    # 30 minutes after last run: DataRefresh should NOT be due now, but in 30 minutes
    now_plus_30m = now + timedelta(minutes=30)
    assert refresh_job2.next_run(now_plus_30m) == now + timedelta(hours=1)

    # 5 days after last run: Retention should be due in 2 days, NOT in 7 days
    now_plus_5d = now + timedelta(days=5)
    assert retention_job2.next_run(now_plus_5d) == now + timedelta(days=7)


def test_r5_expire_pending_job_deadlines(tmp_path):
    """ExpirePendingOrdersJob returns None if no pending orders, or earliest expiration."""
    db = OfficeDB(tmp_path / "test.db")
    office = build_test_office(db=db)
    rt = Runtime(office=office)

    now = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    job = ExpirePendingOrdersJob(rt)

    # With no pending orders, next_run is None
    assert job.next_run(now) is None

    # Insert a pending order created at 10:00 with end of session deadline
    db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={"symbol": "AAPL", "side": "buy", "quantity": "10", "expires_at": "2026-06-01T20:00:00Z"},
        draft_hash="h1",
        approval_status="pending",
        client_order_id="cid_pending_1",
        status="pending",
    )

    next_due = job.next_run(now)
    assert next_due is not None
    assert next_due == datetime(2026, 6, 1, 20, 0, 0, tzinfo=UTC)


def test_r5_release_queued_orders_job_deadlines(tmp_path):
    """ReleaseQueuedOrdersJob returns None if no queued orders, or next market open."""
    db = OfficeDB(tmp_path / "test.db")
    fake_broker = FakeBracketBroker()
    office = build_test_office(db=db, broker=fake_broker)
    rt = Runtime(office=office)

    now = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    job = ReleaseQueuedOrdersJob(rt)

    # No queued orders -> None
    assert job.next_run(now) is None

    # Queue an order
    db.insert_order(
        ticker="AAPL",
        side="buy",
        draft={"symbol": "AAPL", "side": "buy", "quantity": "10"},
        draft_hash="h1",
        approval_status="auto",
        client_order_id="cid_q_1",
        status="queued",
    )

    market_open = datetime(2026, 6, 1, 13, 30, 0, tzinfo=UTC)
    fake_broker.next_market_open = MagicMock(return_value=market_open)

    next_due = job.next_run(now)
    assert next_due == market_open
