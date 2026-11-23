"""Event log and event bus for the single-writer runtime."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from storage.office_db import OfficeDB

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    id: int
    ts: str
    type: str
    actor: str
    subject: str | None
    command_id: str | None
    payload: dict[str, Any]


class Subscription:
    """Thread-safe event subscription queue."""

    def __init__(self, bus: EventBus, maxsize: int = 1000) -> None:
        self._bus = bus
        self._queue: Queue[Event] = Queue(maxsize=maxsize)
        self._active = True

    def put(self, event: Event) -> None:
        if not self._active:
            return
        try:
            self._queue.put_nowait(event)
        except Exception:
            # Drop or slow client
            logger.warning("Subscription queue full, dropping event %s", event.id)

    def get(self, timeout: float | None = None) -> Event:
        """Get next event, raising queue.Empty if timeout occurs."""
        return self._queue.get(timeout=timeout)

    def unsubscribe(self) -> None:
        self._active = False
        self._bus._remove_subscription(self)

    def __iter__(self) -> Iterator[Event]:
        while self._active:
            try:
                yield self.get(timeout=1.0)
            except Empty:
                continue

    def __enter__(self) -> Subscription:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.unsubscribe()


class EventBus:
    """In-process thread-safe publish-subscribe event bus."""

    def __init__(self) -> None:
        self._subscribers: list[Subscription] = []
        self._listeners: list[Any] = []
        self._lock = threading.Lock()

    def subscribe(self, maxsize: int = 1000) -> Subscription:
        sub = Subscription(bus=self, maxsize=maxsize)
        with self._lock:
            self._subscribers.append(sub)
        return sub

    def _remove_subscription(self, sub: Subscription) -> None:
        with self._lock:
            if sub in self._subscribers:
                self._subscribers.remove(sub)

    def add_listener(self, listener: Any) -> None:
        with self._lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: Any) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def publish(self, event: Event) -> None:
        with self._lock:
            subs = list(self._subscribers)
            listeners = list(self._listeners)
        for sub in subs:
            sub.put(event)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Error in event bus listener")


class EventLog:
    """Append-only event log backed by SQLite events table with after-commit bus notification."""

    def __init__(self, db: OfficeDB, bus: EventBus | None = None) -> None:
        self.db = db
        self.bus = bus

    def append(
        self,
        type: str,
        subject: str | None,
        payload: Any,
        actor: str,
        command_id: str | None = None,
    ) -> Event:
        from storage.office_db import utc_now_iso

        ts = utc_now_iso()
        payload_dict = payload if isinstance(payload, dict) else (
            payload.model_dump() if hasattr(payload, "model_dump") else {"data": payload}
        )
        payload_json = json.dumps(payload_dict, default=str)

        cursor = self.db.connection.execute(
            """
            INSERT INTO events (ts, type, actor, subject, command_id, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ts, type, actor, subject, command_id, payload_json),
        )
        event_id = int(cursor.lastrowid)

        event = Event(
            id=event_id,
            ts=ts,
            type=type,
            actor=actor,
            subject=subject,
            command_id=command_id,
            payload=payload_dict,
        )

        if self.bus is not None:
            self.db.add_on_commit(lambda: self.bus.publish(event))

        return event

    def since(self, after_id: int | None = 0, limit: int | None = None) -> list[Event]:
        after = after_id if after_id is not None else 0
        if limit is not None:
            query = """
                SELECT id, ts, type, actor, subject, command_id, payload
                FROM events
                WHERE id > ?
                ORDER BY id ASC
                LIMIT ?
            """
            rows = self.db.connection.execute(query, (after, limit)).fetchall()
        else:
            query = """
                SELECT id, ts, type, actor, subject, command_id, payload
                FROM events
                WHERE id > ?
                ORDER BY id ASC
            """
            rows = self.db.connection.execute(query, (after,)).fetchall()

        events = []
        for row in rows:
            events.append(
                Event(
                    id=int(row["id"]),
                    ts=str(row["ts"]),
                    type=str(row["type"]),
                    actor=str(row["actor"]),
                    subject=row["subject"],
                    command_id=row["command_id"],
                    payload=json.loads(row["payload"]),
                )
            )
        return events
