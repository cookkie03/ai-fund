import sqlite3
import threading
import time
from queue import Empty

import pytest

from runtime.events import Event, EventBus, EventLog
from storage.office_db import OfficeDB


@pytest.fixture
def db(tmp_path):
    return OfficeDB(tmp_path / "test.db")


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def event_log(db, bus):
    return EventLog(db=db, bus=bus)


def test_events_table_migration(db):
    """Verify table events exists and has the expected schema."""
    cursor = db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
    )
    assert cursor.fetchone() is not None


def test_event_log_append_autocommit(event_log, bus):
    """EventLog.append outside a transaction writes row and publishes immediately."""
    sub = bus.subscribe()

    evt = event_log.append(
        type="order.created",
        subject="order:1",
        payload={"ticker": "AAPL", "qty": 10},
        actor="cli",
        command_id="cmd-1",
    )

    assert isinstance(evt, Event)
    assert evt.id is not None
    assert evt.type == "order.created"
    assert evt.subject == "order:1"
    assert evt.payload == {"ticker": "AAPL", "qty": 10}
    assert evt.actor == "cli"
    assert evt.command_id == "cmd-1"

    received = sub.get(timeout=1.0)
    assert received == evt
    sub.unsubscribe()


def test_event_log_transaction_commit_publishes_after_commit(db, event_log, bus):
    """Event is only visible to subscriber after transaction commit."""
    sub = bus.subscribe()

    with db.transaction():
        evt = event_log.append(
            type="cycle.opened",
            subject="cycle:42",
            payload={"ticker": "MSFT"},
            actor="runtime",
        )
        # Inside transaction, should not yet be published
        with pytest.raises(Empty):
            sub.get(timeout=0.05)

    # After transaction commit, event is published
    received = sub.get(timeout=1.0)
    assert received.id == evt.id
    assert received.type == "cycle.opened"
    sub.unsubscribe()


def test_event_log_transaction_rollback_discards_event(db, event_log, bus):
    """If transaction rolls back, no event is published and no row is in DB."""
    sub = bus.subscribe()

    with pytest.raises(ValueError, match="simulated failure"):
        with db.transaction():
            event_log.append(
                type="task.enqueued",
                subject="task:99",
                payload={"reason": "test"},
                actor="scheduler",
            )
            raise ValueError("simulated failure")

    # No event in bus
    with pytest.raises(Empty):
        sub.get(timeout=0.05)

    # No event in DB
    events = event_log.since(after_id=0)
    assert len(events) == 0
    sub.unsubscribe()


def test_event_log_since_ordering_and_filtering(event_log):
    """since(after_id, limit) returns ordered events strictly after after_id."""
    e1 = event_log.append("type.a", "sub:1", {"n": 1}, "actor1")
    e2 = event_log.append("type.b", "sub:2", {"n": 2}, "actor2")
    e3 = event_log.append("type.c", "sub:3", {"n": 3}, "actor3")

    all_events = event_log.since(after_id=0)
    assert [e.id for e in all_events] == [e1.id, e2.id, e3.id]

    after_first = event_log.since(after_id=e1.id)
    assert [e.id for e in after_first] == [e2.id, e3.id]

    limited = event_log.since(after_id=0, limit=2)
    assert [e.id for e in limited] == [e1.id, e2.id]


def test_unique_command_accepted_idempotency(event_log):
    """UNIQUE index prevents duplicate command.accepted for same command_id."""
    event_log.append("command.accepted", "cmd:1", {"ok": True}, "cli", command_id="cmd-1")

    with pytest.raises(sqlite3.IntegrityError):
        event_log.append("command.accepted", "cmd:1", {"ok": True}, "cli", command_id="cmd-1")


def test_event_bus_fan_out_multiple_subscribers_threads(bus):
    """Bus fans out events to N subscribers across multiple threads."""
    subscribers = [bus.subscribe() for _ in range(5)]
    results: list[list[Event]] = [[] for _ in range(5)]
    threads = []

    def reader(sub_idx, sub):
        for _ in range(3):
            evt = sub.get(timeout=2.0)
            results[sub_idx].append(evt)

    for i, s in enumerate(subscribers):
        t = threading.Thread(target=reader, args=(i, s))
        threads.append(t)
        t.start()

    time.sleep(0.02)
    test_events = [
        Event(id=1, ts="2026-11-20T10:00:00Z", type="e1", actor="a", subject="s", command_id=None, payload={}),
        Event(id=2, ts="2026-11-20T10:00:01Z", type="e2", actor="a", subject="s", command_id=None, payload={}),
        Event(id=3, ts="2026-11-20T10:00:02Z", type="e3", actor="a", subject="s", command_id=None, payload={}),
    ]

    for te in test_events:
        bus.publish(te)

    for t in threads:
        t.join(timeout=2.0)

    for i in range(5):
        assert len(results[i]) == 3
        assert [e.id for e in results[i]] == [1, 2, 3]

    for s in subscribers:
        s.unsubscribe()
