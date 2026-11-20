"""Core Runtime orchestrating single-writer execution, event log, read model, and lifecycle."""

from __future__ import annotations

import fcntl
import json
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from runtime.commands import (
    AddWatchlist,
    ApproveOrder,
    CommandResult,
    EnqueueTask,
    Halt,
    IngestAlert,
    MarkInboxRead,
    ReconcileBroker,
    RefreshData,
    RejectOrder,
    RemoveWatchlist,
    Resume,
    Say,
)
from runtime.events import Event, EventBus, EventLog
from runtime.handlers import (
    handle_add_watchlist,
    handle_approve_order,
    handle_enqueue_task,
    handle_halt,
    handle_ingest_alert,
    handle_mark_inbox_read,
    handle_reconcile_broker,
    handle_refresh_data,
    handle_reject_order,
    handle_remove_watchlist,
    handle_resume,
    handle_say,
)
from runtime.jobs import (
    DataRefreshJob,
    ExpirePendingOrdersJob,
    MarketAnalystFixedJob,
    ReleaseQueuedOrdersJob,
    RetentionJob,
)
from runtime.queries import ReadModel
from runtime.scheduler import Scheduler

if TYPE_CHECKING:
    from workflows.office import Office

logger = logging.getLogger(__name__)


@dataclass
class RuntimeContext:
    office: Office
    event_log: EventLog
    event_bus: EventBus
    runtime: Runtime


_HANDLER_MAP = {
    EnqueueTask: handle_enqueue_task,
    Say: handle_say,
    AddWatchlist: handle_add_watchlist,
    RemoveWatchlist: handle_remove_watchlist,
    ApproveOrder: handle_approve_order,
    RejectOrder: handle_reject_order,
    Halt: handle_halt,
    Resume: handle_resume,
    ReconcileBroker: handle_reconcile_broker,
    RefreshData: handle_refresh_data,
    MarkInboxRead: handle_mark_inbox_read,
    IngestAlert: handle_ingest_alert,
}


class Runtime:
    """The single-writer, event-driven runtime process."""

    @classmethod
    def from_settings(
        cls,
        settings: Any = None,
        env: Any = None,
    ) -> Runtime:
        from bootstrap import build_office
        from brokers.alpaca import get_alpaca_credentials
        from runtime.broker_stream import AlpacaTradeUpdateStream

        office = build_office(settings=settings, env=env)
        creds = get_alpaca_credentials(env=env)
        stream = None
        broker_configured = creds["configured"]

        if broker_configured:
            def _reconcile() -> None:
                if hasattr(office, "order_flow") and office.order_flow:
                    office.order_flow.sync_broker_orders()
                try:
                    office.refresh_data(force=False, kinds=["portfolio"])
                except Exception:
                    pass

            stream = AlpacaTradeUpdateStream(
                api_key=creds["api_key"],
                secret_key=creds["secret_key"],
                paper=creds["paper"],
                trading_url=creds["trading_url"],
                on_trade_update=office.order_flow.apply_broker_update if hasattr(office, "order_flow") and office.order_flow else None,
                on_reconnect=_reconcile,
            )

        rt = cls(office=office, broker_stream=stream)
        rt.broker_configured = broker_configured
        return rt

    def __init__(
        self,
        office: Office,
        broker_stream: Any | None = None,
    ) -> None:
        self.office = office
        self.broker_stream = broker_stream
        self.bus = EventBus()
        self.event_log = EventLog(db=office.db, bus=self.bus)
        self.read = ReadModel(db_path=office.db.path, runtime=self)

        self.office.event_log = self.event_log
        if hasattr(self.office, "order_flow") and self.office.order_flow:
            self.office.order_flow.event_log = self.event_log
        if hasattr(self.office, "halt") and self.office.halt:
            self.office.halt._event_log = self.event_log
        if hasattr(self.office, "trade_manager") and self.office.trade_manager:
            self.office.trade_manager.event_log = self.event_log

        self._ctx = RuntimeContext(
            office=self.office,
            event_log=self.event_log,
            event_bus=self.bus,
            runtime=self,
        )

        self._lock_file: Any = None
        self._command_lock = threading.Lock()
        self.broker_configured = broker_stream is not None
        self.broker_stream_connected = False
        self.broker_stream_error: str | None = None
        self._running = False

        self.scheduler = Scheduler(runtime=self, clock=office.clock)
        self.scheduler.register_job(DataRefreshJob(self))
        self.scheduler.register_job(RetentionJob(self))
        self.scheduler.register_job(MarketAnalystFixedJob(self))
        self.scheduler.register_job(ExpirePendingOrdersJob(self))
        self.scheduler.register_job(ReleaseQueuedOrdersJob(self))
        self.scheduler.bind_events()

    def reconcile_broker(self) -> None:
        """Run broker reconciliation: sync orders and refresh portfolio."""
        if hasattr(self.office, "order_flow") and self.office.order_flow:
            try:
                self.office.order_flow.sync_broker_orders()
            except Exception:
                logger.exception("Broker order sync failed during reconciliation")
        try:
            self.office.refresh_data(force=False, kinds=["portfolio"])
        except Exception:
            logger.exception("Portfolio refresh failed during reconciliation")

    def start(self) -> None:
        """Acquire single-writer process lock and start internal services."""
        if self._running:
            return

        db_path = self.office.db.path
        if db_path != Path(":memory:") and self._lock_file is None:
            lock_path = db_path.with_suffix(".db.lock")
            self._lock_file = open(lock_path, "w")
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as err:
                self._lock_file.close()
                self._lock_file = None
                raise RuntimeError(
                    f"Another Runtime process is already running on database: {db_path}"
                ) from err

        self._running = True
        self.reconcile_broker()
        if self.broker_stream is not None:
            try:
                self.broker_stream.start()
                self.broker_stream_connected = getattr(self.broker_stream, "connected", True)
            except Exception as exc:
                self.broker_stream_connected = False
                self.broker_stream_error = str(exc)
                logger.exception("Failed to start broker stream")

        self.event_log.append(
            type="runtime.started",
            subject="runtime",
            payload={"db_path": str(db_path)},
            actor="runtime",
        )

    def stop(self) -> None:
        """Stop background services and release single-writer lock."""
        if not self._running:
            return

        if self.broker_stream is not None:
            try:
                self.broker_stream.stop()
            except Exception:
                pass
            self.broker_stream_connected = False

        try:
            self.event_log.append(
                type="runtime.stopped",
                subject="runtime",
                payload={},
                actor="runtime",
            )
        except Exception:
            pass

        self._running = False

        if self._lock_file is not None:
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
            except Exception:
                pass
            self._lock_file = None

    def execute(self, cmd: Any, actor: str, command_id: str | None = None) -> CommandResult:
        handler = _HANDLER_MAP.get(cmd.__class__)
        if not handler:
            return CommandResult(ok=False, reasons=[f"Unknown command type: {cmd.__class__.__name__}"])

        with self._command_lock:
            # 1. Idempotency check: if command_id exists, return saved result
            if command_id:
                existing = self._find_saved_command_result(command_id)
                if existing is not None:
                    return existing

            # 2. Execute handler, then log result in a database transaction
            try:
                result = handler(self._ctx, cmd, actor)
                with self.office.db.transaction():
                    if result.ok:
                        self.event_log.append(
                            type="command.accepted",
                            subject=f"command:{cmd.__class__.__name__}",
                            payload={
                                "command": cmd.__class__.__name__,
                                "ok": True,
                                "data": result.data,
                                "reasons": result.reasons,
                            },
                            actor=actor,
                            command_id=command_id,
                        )
                    else:
                        self.event_log.append(
                            type="command.rejected",
                            subject=f"command:{cmd.__class__.__name__}",
                            payload={
                                "command": cmd.__class__.__name__,
                                "ok": False,
                                "data": result.data,
                                "reasons": result.reasons,
                            },
                            actor=actor,
                            command_id=command_id,
                        )
                return result
            except Exception as exc:
                logger.exception("Error executing command %s", cmd.__class__.__name__)
                # Outside handler: log rejection
                try:
                    with self.office.db.transaction():
                        self.event_log.append(
                            type="command.rejected",
                            subject=f"command:{cmd.__class__.__name__}",
                            payload={
                                "command": cmd.__class__.__name__,
                                "ok": False,
                                "reasons": [str(exc)],
                                "data": {},
                            },
                            actor=actor,
                            command_id=command_id,
                        )
                except Exception:
                    pass
                return CommandResult(ok=False, reasons=[str(exc)])

    def _find_saved_command_result(self, command_id: str) -> CommandResult | None:
        row = self.office.db.connection.execute(
            """
            SELECT payload FROM events
            WHERE command_id = ? AND type = 'command.accepted'
            LIMIT 1
            """,
            (command_id,),
        ).fetchone()

        if not row:
            return None

        payload = json.loads(row["payload"])
        return CommandResult(
            ok=bool(payload.get("ok", True)),
            data=payload.get("data", {}),
            reasons=payload.get("reasons", []),
        )

    def subscribe(self, after_id: int | None = None) -> Iterator[Event]:
        """Subscribe to events, replaying historical events since after_id before streaming live."""
        sub = self.bus.subscribe()
        try:
            if after_id is not None:
                yield from self.event_log.since(after_id=after_id)

            yield from sub
        finally:
            sub.unsubscribe()
