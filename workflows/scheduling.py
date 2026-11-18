"""Pure logic for Scheduled tasks and Trigger engine routing/dispatching.

Requirements:
- Pure functions, no I/O, no DB, no LLM, no network.
- Frozen dataclasses.
- Decimal for money/prices.
- Type hints and ruff line length <= 100.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal


class TaskSource(StrEnum):
    """Source of a scheduled task."""

    ALERT_PRICE = "alert_price"
    ALERT_CALENDAR = "alert_calendar"
    ALERT_EARNINGS = "alert_earnings"
    AGENT = "agent"
    MARKET_MESSAGE = "market_message"
    MANUAL = "manual"
    FIXED_BASE = "fixed_base"


@dataclass(frozen=True)
class ScheduledTask:
    """Frozen dataclass representing an invocation scheduled for an agent."""

    agent: str
    chat: str
    when: datetime
    source: TaskSource
    reason: str
    data: dict[str, Any] = field(default_factory=dict)
    merged_from: tuple[str, ...] = field(default_factory=tuple)
    task_id: str = ""
    attempts: int = 0
    next_attempt_not_before: datetime | None = None

    def __post_init__(self) -> None:
        if self.when.utcoffset() is None or self.when.tzinfo != UTC:
            raise ValueError(f"Task 'when' must be a UTC datetime, got {self.when}")
        if self.next_attempt_not_before is not None:
            if (
                self.next_attempt_not_before.utcoffset() is None
                or self.next_attempt_not_before.tzinfo != UTC
            ):
                raise ValueError("Task 'next_attempt_not_before' must be a UTC datetime")


TradingCalendar = Any | Callable[[date], bool]


def _is_trading_day(cal: TradingCalendar, day: date) -> bool:
    if hasattr(cal, "is_trading_day"):
        return bool(cal.is_trading_day(day))
    if callable(cal):
        return bool(cal(day))
    return day.weekday() < 5


def _add_trading_days(start_date: date, count: int, calendar: TradingCalendar) -> date:
    """Advance `count` trading days forward from `start_date`."""
    current = start_date
    added = 0
    while added < count:
        current += timedelta(days=1)
        if _is_trading_day(calendar, current):
            added += 1
    return current


def clamp_schedule_date(
    requested: datetime,
    now: datetime,
    min_trading_days: int,
    max_trading_days: int,
    calendar: TradingCalendar,
) -> datetime:
    """Limits an agent-chosen date between min and max trading days from now."""
    if requested.utcoffset() is None or now.utcoffset() is None:
        raise ValueError("Dates must be timezone-aware (UTC)")

    min_date = _add_trading_days(now.date(), min_trading_days, calendar)
    max_date = _add_trading_days(now.date(), max_trading_days, calendar)

    req_date = requested.date()

    if req_date < min_date:
        return datetime.combine(min_date, requested.time(), tzinfo=requested.tzinfo)
    if req_date > max_date:
        return datetime.combine(max_date, requested.time(), tzinfo=requested.tzinfo)
    return requested


def merge_tasks(tasks: Sequence[ScheduledTask]) -> tuple[ScheduledTask, ...]:
    """Fuse queued tasks for the same agent+chat into one composite task.

    Earliest 'when', reasons concatenated, data merged under a list, merged_from set.
    Tasks for different chats or agents are untouched. Deterministic ordering.
    """
    if not tasks:
        return ()

    # Group preserving deterministic order of appearance
    groups: dict[tuple[str, str], list[ScheduledTask]] = {}
    for task in tasks:
        key = (task.agent, task.chat)
        if key not in groups:
            groups[key] = []
        groups[key].append(task)

    merged: list[ScheduledTask] = []
    # Deterministic sort of groups by key (agent, chat)
    for (agent, chat), group in sorted(groups.items(), key=lambda item: item[0]):
        if len(group) == 1:
            merged.append(group[0])
            continue

        # Earliest when
        earliest_task = min(group, key=lambda t: t.when)
        earliest_when = earliest_task.when

        # Concatenate reasons in order of when, then task_id
        ordered_group = sorted(group, key=lambda t: (t.when, t.task_id))
        reasons = [t.reason for t in ordered_group if t.reason]
        combined_reason = " | ".join(reasons)

        # Collect merged_from task ids
        merged_ids: list[str] = []
        for t in ordered_group:
            if t.merged_from:
                merged_ids.extend(t.merged_from)
            elif t.task_id:
                merged_ids.append(t.task_id)

        # Data merged under a list
        combined_data: dict[str, Any] = {
            "items": [t.data for t in ordered_group if t.data],
        }

        composite = ScheduledTask(
            task_id=earliest_task.task_id or (merged_ids[0] if merged_ids else ""),
            agent=agent,
            chat=chat,
            when=earliest_when,
            source=earliest_task.source,
            reason=combined_reason,
            data=combined_data,
            merged_from=tuple(merged_ids),
        )
        merged.append(composite)

    return tuple(merged)


def route_task(
    task: ScheduledTask, open_cycles: set[str]
) -> Literal["new_cycle", "message_into_open_cycle"]:
    """Route a task to a new cycle or as a message into an open cycle."""
    if task.chat in open_cycles:
        return "message_into_open_cycle"
    return "new_cycle"


_SOURCE_LABELS_IT: dict[TaskSource, str] = {
    TaskSource.ALERT_PRICE: "Alert Prezzo",
    TaskSource.ALERT_CALENDAR: "Alert Calendario",
    TaskSource.ALERT_EARNINGS: "Alert Trimestrale",
    TaskSource.AGENT: "Controllo Programmato Agente",
    TaskSource.MARKET_MESSAGE: "Messaggio Market Analyst",
    TaskSource.MANUAL: "Richiesta Manuale",
    TaskSource.FIXED_BASE: "Attivazione Fissa di Base",
}


def _format_data_it(data: dict[str, Any]) -> str:
    if not data:
        return "Nessun dato aggiuntivo"
    lines = []
    for k, v in sorted(data.items(), key=lambda x: str(x[0])):
        if isinstance(v, Decimal):
            lines.append(f"- {k}: {v}")
        elif isinstance(v, list):
            lines.append(f"- {k}: {len(v)} elementi")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def translate_task(task: ScheduledTask) -> str:
    """Deterministic Italian translator producing PM opening prompt text."""
    fonte_label = _SOURCE_LABELS_IT.get(task.source, task.source.value)
    dati_formatted = _format_data_it(task.data)
    return (
        f"Fonte: {fonte_label}\n"
        f"Ticker: {task.chat}\n"
        f"Motivo: {task.reason}\n"
        f"Dati:\n{dati_formatted}"
    )


@dataclass(frozen=True)
class DueCursor:
    """Cursor tracking delivery of due tasks."""

    last_delivered_when: datetime | None = None


def due_tasks(
    tasks: Sequence[ScheduledTask],
    now: datetime,
    cursor: DueCursor,
    accepted_ids: set[str] | None = None,
) -> tuple[tuple[ScheduledTask, ...], DueCursor]:
    """Returns tasks with when <= now and when > cursor boundary.

    Backoff check: tasks with next_attempt_not_before > now are excluded.
    Cursor advances only when the caller confirms acceptance via accepted_ids.
    """
    due_list: list[ScheduledTask] = []
    for t in tasks:
        if cursor.last_delivered_when is not None and t.when <= cursor.last_delivered_when:
            continue
        if t.when > now:
            continue
        if t.next_attempt_not_before is not None and t.next_attempt_not_before > now:
            continue
        due_list.append(t)

    # Sort deterministically by when, then task_id
    due_sorted = tuple(sorted(due_list, key=lambda t: (t.when, t.task_id)))

    # Compute new cursor
    new_last_delivered = cursor.last_delivered_when
    if accepted_ids:
        accepted_whens = [t.when for t in due_sorted if t.task_id in accepted_ids]
        if accepted_whens:
            max_accepted = max(accepted_whens)
            if new_last_delivered is None or max_accepted > new_last_delivered:
                new_last_delivered = max_accepted

    return due_sorted, DueCursor(last_delivered_when=new_last_delivered)


def record_task_failure(task: ScheduledTask, now: datetime) -> ScheduledTask:
    """Calculates backoff for a failed task delivery and increments attempts.

    Backoff formula: at least 60s * 2**attempts capped at 1h (3600s).
    """
    new_attempts = task.attempts + 1
    delay_seconds = min(60 * (2**task.attempts), 3600)
    next_attempt = now + timedelta(seconds=delay_seconds)
    return replace(task, attempts=new_attempts, next_attempt_not_before=next_attempt)
