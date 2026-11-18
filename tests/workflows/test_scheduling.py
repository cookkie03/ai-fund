from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from workflows.scheduling import (
    DueCursor,
    ScheduledTask,
    TaskSource,
    clamp_schedule_date,
    due_tasks,
    merge_tasks,
    route_task,
    translate_task,
)


class FakeCalendar:
    """Simple trading calendar that provides trading days (weekdays)."""

    def __init__(self, trading_days: list[datetime.date] | None = None):
        self._trading_days = set(trading_days) if trading_days is not None else None

    def is_trading_day(self, d: datetime.date) -> bool:
        if self._trading_days is not None:
            return d in self._trading_days
        return d.weekday() < 5  # Mon-Fri default


def test_scheduled_task_frozen_dataclass():
    now = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    task = ScheduledTask(
        task_id="task-1",
        agent="Portfolio Manager",
        chat="AAPL",
        when=now,
        source=TaskSource.ALERT_PRICE,
        reason="Price crossed MA50",
        data={"price": Decimal("150.50"), "threshold": Decimal("150.00")},
        merged_from=("task-orig-1", "task-orig-2"),
    )
    assert task.agent == "Portfolio Manager"
    assert task.chat == "AAPL"
    assert task.when == now
    assert task.source == TaskSource.ALERT_PRICE
    assert task.reason == "Price crossed MA50"
    assert task.data == {"price": Decimal("150.50"), "threshold": Decimal("150.00")}
    assert task.merged_from == ("task-orig-1", "task-orig-2")
    assert task.attempts == 0
    assert task.next_attempt_not_before is None

    with pytest.raises(Exception):
        task.reason = "modified"  # frozen


def test_scheduled_task_utc_enforcement():
    naive_dt = datetime(2026, 11, 18, 10, 0)
    with pytest.raises(ValueError, match="UTC"):
        ScheduledTask(
            task_id="t1",
            agent="Portfolio Manager",
            chat="AAPL",
            when=naive_dt,
            source=TaskSource.MANUAL,
            reason="test",
        )


def test_clamp_schedule_date_within_bounds():
    calendar = FakeCalendar()
    # Wednesday 2026-11-18 10:00 UTC
    now = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    # Requested: Friday 2026-11-20 (2 trading days later)
    requested = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    clamped = clamp_schedule_date(requested, now, min_trading_days=1, max_trading_days=5, calendar=calendar)
    assert clamped == requested


def test_clamp_schedule_date_below_min():
    calendar = FakeCalendar()
    now = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)  # Wed
    requested = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)  # same day (< 1 trading day)
    clamped = clamp_schedule_date(requested, now, min_trading_days=1, max_trading_days=5, calendar=calendar)
    # 1 trading day from Wed is Thursday 2026-11-19, keeping requested time (or min boundary)
    assert clamped.date() >= datetime(2026, 11, 19).date()


def test_clamp_schedule_date_above_max():
    calendar = FakeCalendar()
    now = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)  # Wed
    # 10 trading days later
    requested = datetime(2026, 12, 18, 10, 0, tzinfo=UTC)
    clamped = clamp_schedule_date(requested, now, min_trading_days=1, max_trading_days=5, calendar=calendar)
    # 5 trading days from Wed Nov 18: Thu 19 (1), Fri 20 (2), Mon 23 (3), Tue 24 (4), Wed 25 (5)
    assert clamped.date() == datetime(2026, 11, 25).date()


def test_clamp_schedule_date_with_callable_calendar():
    # Test calendar as a callable or object with is_trading_day
    calendar = lambda d: d.weekday() < 5
    now = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    requested = datetime(2026, 12, 18, 10, 0, tzinfo=UTC)
    clamped = clamp_schedule_date(requested, now, min_trading_days=1, max_trading_days=2, calendar=calendar)
    # 2 trading days: Thu 19, Fri 20
    assert clamped.date() == datetime(2026, 11, 20).date()


def test_merge_tasks_same_agent_and_chat():
    t1 = datetime(2026, 11, 18, 14, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)  # earlier
    task1 = ScheduledTask(
        task_id="t1",
        agent="Portfolio Manager",
        chat="AAPL",
        when=t1,
        source=TaskSource.ALERT_PRICE,
        reason="Price dropped 5%",
        data={"price": Decimal("140.00")},
    )
    task2 = ScheduledTask(
        task_id="t2",
        agent="Portfolio Manager",
        chat="AAPL",
        when=t2,
        source=TaskSource.ALERT_EARNINGS,
        reason="Earnings release",
        data={"eps": Decimal("1.25")},
    )

    merged = merge_tasks((task1, task2))
    assert len(merged) == 1
    m = merged[0]
    assert m.agent == "Portfolio Manager"
    assert m.chat == "AAPL"
    assert m.when == t2  # earliest 'when'
    assert m.merged_from == ("t1", "t2") or m.merged_from == ("t2", "t1")
    assert "Price dropped 5%" in m.reason
    assert "Earnings release" in m.reason
    assert "items" in m.data or isinstance(m.data.get("items"), list)
    assert len(m.data["items"]) == 2


def test_merge_tasks_different_chats_untouched():
    t = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    task1 = ScheduledTask(
        task_id="t1",
        agent="Portfolio Manager",
        chat="AAPL",
        when=t,
        source=TaskSource.MANUAL,
        reason="Check AAPL",
    )
    task2 = ScheduledTask(
        task_id="t2",
        agent="Portfolio Manager",
        chat="MSFT",
        when=t,
        source=TaskSource.MANUAL,
        reason="Check MSFT",
    )
    merged = merge_tasks((task1, task2))
    assert len(merged) == 2
    chats = {task.chat for task in merged}
    assert chats == {"AAPL", "MSFT"}


def test_merge_tasks_deterministic_ordering():
    t = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    tasks = [
        ScheduledTask(task_id=f"t{i}", agent="Portfolio Manager", chat=c, when=t, source=TaskSource.MANUAL, reason=f"r{i}")
        for i, c in enumerate(["NVDA", "AAPL", "GOOGL", "AAPL", "MSFT"])
    ]
    merged1 = merge_tasks(tuple(tasks))
    merged2 = merge_tasks(tuple(tasks))
    assert merged1 == merged2
    # Check that AAPL was merged and distinct chats remain in deterministic order
    assert len(merged1) == 4


def test_route_task():
    task_aapl = ScheduledTask(
        task_id="t1",
        agent="Portfolio Manager",
        chat="AAPL",
        when=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        source=TaskSource.ALERT_PRICE,
        reason="Alert",
    )
    assert route_task(task_aapl, open_cycles={"AAPL", "MSFT"}) == "message_into_open_cycle"
    assert route_task(task_aapl, open_cycles={"NVDA", "MSFT"}) == "new_cycle"
    assert route_task(task_aapl, open_cycles=set()) == "new_cycle"


def test_translators_italian_uniform_sections():
    task = ScheduledTask(
        task_id="t1",
        agent="Portfolio Manager",
        chat="AAPL",
        when=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        source=TaskSource.ALERT_PRICE,
        reason="Prezzo sotto MA200",
        data={"prezzo": Decimal("145.00"), "ma200": Decimal("150.00")},
    )
    prompt = translate_task(task)
    assert "Fonte:" in prompt
    assert "Ticker:" in prompt
    assert "Motivo:" in prompt
    assert "Dati:" in prompt
    assert "AAPL" in prompt
    assert "Prezzo sotto MA200" in prompt


def test_translators_all_sources():
    sources = [
        TaskSource.ALERT_PRICE,
        TaskSource.ALERT_CALENDAR,
        TaskSource.ALERT_EARNINGS,
        TaskSource.AGENT,
        TaskSource.MARKET_MESSAGE,
        TaskSource.MANUAL,
        TaskSource.FIXED_BASE,
    ]
    for source in sources:
        task = ScheduledTask(
            task_id="test",
            agent="Portfolio Manager",
            chat="AAPL",
            when=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
            source=source,
            reason="Motivo di test",
            data={"dettaglio": "valore"},
        )
        prompt = translate_task(task)
        assert "Fonte:" in prompt
        assert "Ticker:" in prompt
        assert "Motivo:" in prompt
        assert "Dati:" in prompt


def test_due_tasks_basic_filtering():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    cursor = DueCursor(last_delivered_when=datetime(2026, 11, 18, 9, 0, tzinfo=UTC))

    t_past_before_cursor = ScheduledTask(
        task_id="t0",
        agent="Portfolio Manager",
        chat="A",
        when=datetime(2026, 11, 18, 8, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="past",
    )
    t_due1 = ScheduledTask(
        task_id="t1",
        agent="Portfolio Manager",
        chat="B",
        when=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="due1",
    )
    t_due2 = ScheduledTask(
        task_id="t2",
        agent="Portfolio Manager",
        chat="C",
        when=datetime(2026, 11, 18, 11, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="due2",
    )
    t_future = ScheduledTask(
        task_id="t3",
        agent="Portfolio Manager",
        chat="D",
        when=datetime(2026, 11, 18, 13, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="future",
    )

    tasks = (t_past_before_cursor, t_due1, t_due2, t_future)
    due, new_cursor = due_tasks(tasks, now=now, cursor=cursor, accepted_ids={"t1", "t2"})
    assert tuple(t.task_id for t in due) == ("t1", "t2")
    assert new_cursor.last_delivered_when == datetime(2026, 11, 18, 11, 0, tzinfo=UTC)


def test_due_tasks_cursor_advances_only_on_accepted_ids():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    cursor = DueCursor(last_delivered_when=datetime(2026, 11, 18, 9, 0, tzinfo=UTC))

    t1 = ScheduledTask(
        task_id="t1",
        agent="Portfolio Manager",
        chat="B",
        when=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="due1",
    )
    t2 = ScheduledTask(
        task_id="t2",
        agent="Portfolio Manager",
        chat="C",
        when=datetime(2026, 11, 18, 11, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="due2",
    )
    tasks = (t1, t2)
    # Caller only accepted t1, not t2
    due, new_cursor = due_tasks(tasks, now=now, cursor=cursor, accepted_ids={"t1"})
    assert tuple(t.task_id for t in due) == ("t1", "t2")
    assert new_cursor.last_delivered_when == datetime(2026, 11, 18, 10, 0, tzinfo=UTC)


def test_due_tasks_backoff_and_failed_attempts():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    cursor = DueCursor()

    # Task that failed once and backoff is in the future
    t_failed_waiting = ScheduledTask(
        task_id="t1",
        agent="Portfolio Manager",
        chat="AAPL",
        when=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="retry",
        attempts=1,
        next_attempt_not_before=datetime(2026, 11, 18, 12, 30, tzinfo=UTC),
    )
    # Task that failed once but backoff time has passed
    t_failed_ready = ScheduledTask(
        task_id="t2",
        agent="Portfolio Manager",
        chat="MSFT",
        when=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="retry ready",
        attempts=2,
        next_attempt_not_before=datetime(2026, 11, 18, 11, 50, tzinfo=UTC),
    )

    due, _ = due_tasks((t_failed_waiting, t_failed_ready), now=now, cursor=cursor, accepted_ids=None)
    assert tuple(t.task_id for t in due) == ("t2",)


def test_record_task_failure_backoff():
    from workflows.scheduling import record_task_failure

    task = ScheduledTask(
        task_id="t1",
        agent="Portfolio Manager",
        chat="AAPL",
        when=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="test",
        attempts=0,
    )
    now = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    failed1 = record_task_failure(task, now=now)
    assert failed1.attempts == 1
    # 60s * 2^0 = 60s
    assert failed1.next_attempt_not_before == now + timedelta(seconds=60)

    failed2 = record_task_failure(failed1, now=now)
    assert failed2.attempts == 2
    # 60s * 2^1 = 120s
    assert failed2.next_attempt_not_before == now + timedelta(seconds=120)

    # Test capping at 1 hour (3600s)
    high_attempt_task = ScheduledTask(
        task_id="t_high",
        agent="PM",
        chat="A",
        when=datetime(2026, 11, 18, 10, 0, tzinfo=UTC),
        source=TaskSource.MANUAL,
        reason="test",
        attempts=10,
    )
    failed_capped = record_task_failure(high_attempt_task, now=now)
    assert failed_capped.attempts == 11
    assert failed_capped.next_attempt_not_before == now + timedelta(seconds=3600)
