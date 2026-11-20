"""HTTP and Server-Sent Events (SSE) transport layer for the Runtime."""

from __future__ import annotations

import asyncio
import json
import logging
from queue import Empty
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from runtime.commands import (
    AddWatchlist,
    ApproveOrder,
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

if TYPE_CHECKING:
    from runtime.core import Runtime

logger = logging.getLogger(__name__)

_COMMAND_MAP: dict[str, type] = {
    "enqueue_task": EnqueueTask,
    "enqueuetask": EnqueueTask,
    "say": Say,
    "add_watchlist": AddWatchlist,
    "addwatchlist": AddWatchlist,
    "remove_watchlist": RemoveWatchlist,
    "removewatchlist": RemoveWatchlist,
    "approve_order": ApproveOrder,
    "approveorder": ApproveOrder,
    "reject_order": RejectOrder,
    "rejectorder": RejectOrder,
    "halt": Halt,
    "resume": Resume,
    "reconcile_broker": ReconcileBroker,
    "reconcilebroker": ReconcileBroker,
    "refresh_data": RefreshData,
    "refreshdata": RefreshData,
    "mark_inbox_read": MarkInboxRead,
    "markinboxread": MarkInboxRead,
    "ingest_alert": IngestAlert,
    "ingestalert": IngestAlert,
}


def create_app(
    runtime: Runtime,
    token: str | None = None,
    host: str = "127.0.0.1",
) -> FastAPI:
    """Create configured FastAPI application exposing Command, Read, and Event ports."""
    is_loopback = host in ("127.0.0.1", "localhost", "::1", "testserver")
    if not is_loopback and not token:
        raise ValueError("Il token è obbligatorio se il bind non è loopback")

    app = FastAPI(title="Trading Agent Runtime API", version="0.1.0")

    async def verify_token(request: Request) -> None:
        if token is not None:
            auth = request.headers.get("Authorization")
            if not auth or not auth.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing or invalid Bearer token")
            provided = auth.removeprefix("Bearer ").strip()
            if provided != token:
                raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/v1/health", dependencies=[Depends(verify_token)])
    async def get_health() -> dict[str, Any]:
        return runtime.read.health().model_dump()

    @app.post("/v1/commands/{name}", dependencies=[Depends(verify_token)])
    async def execute_command(name: str, request: Request) -> Response:
        normalized_name = name.lower().replace("-", "_")
        cmd_cls = _COMMAND_MAP.get(normalized_name)
        if not cmd_cls:
            raise HTTPException(status_code=404, detail=f"Command '{name}' not found")

        try:
            body = await request.json() if await request.body() else {}
            cmd = cmd_cls.model_validate(body)
        except ValidationError as val_err:
            raise HTTPException(status_code=422, detail=val_err.errors()) from val_err
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        command_id = request.headers.get("Idempotency-Key")
        actor = request.headers.get("X-Actor", "client")

        res = await asyncio.to_thread(runtime.execute, cmd, actor, command_id)

        if isinstance(cmd, RefreshData):
            return JSONResponse(status_code=202, content=res.model_dump())
        return JSONResponse(status_code=200, content=res.model_dump())

    @app.get("/v1/read/{name}", dependencies=[Depends(verify_token)])
    async def execute_read(name: str, request: Request) -> Any:
        q = request.query_params
        norm = name.lower().replace("-", "_")

        if norm == "health":
            return runtime.read.health().model_dump()
        elif norm == "portfolio":
            p = runtime.read.portfolio()
            return p.model_dump() if p else None
        elif norm == "orders":
            status = q.get("status")
            limit = int(q.get("limit", 50))
            return [o.model_dump() for o in runtime.read.orders(status=status, limit=limit)]
        elif norm == "order":
            order_id = int(q.get("id") or q.get("order_id", 0))
            ord_obj = runtime.read.order(order_id)
            if not ord_obj:
                raise HTTPException(status_code=404, detail="Order not found")
            return ord_obj.model_dump()
        elif norm == "trades":
            status = q.get("status")
            ticker = q.get("ticker")
            limit = int(q.get("limit", 50))
            return [t.model_dump() for t in runtime.read.trades(status=status, ticker=ticker, limit=limit)]
        elif norm == "cycles":
            ticker = q.get("ticker")
            status = q.get("status")
            limit = int(q.get("limit", 50))
            return [c.model_dump() for c in runtime.read.cycles(ticker=ticker, status=status, limit=limit)]
        elif norm == "cycle":
            cycle_id = int(q.get("id") or q.get("cycle_id", 0))
            c_obj = runtime.read.cycle(cycle_id)
            if not c_obj:
                raise HTTPException(status_code=404, detail="Cycle not found")
            return c_obj.model_dump()
        elif norm == "chat":
            agent = q.get("agent", "")
            topic = q.get("topic", "")
            limit = int(q.get("limit", 50))
            return [m.model_dump() for m in runtime.read.chat(agent=agent, topic=topic, limit=limit)]
        elif norm == "ticker_state":
            ticker = q.get("ticker", "")
            state = runtime.read.ticker_state(ticker)
            return state or {}
        elif norm == "watchlist":
            return [w.model_dump() for w in runtime.read.watchlist()]
        elif norm == "inbox":
            unread_only = q.get("unread_only", "false").lower() in ("true", "1")
            limit = int(q.get("limit", 50))
            return [i.model_dump() for i in runtime.read.inbox(unread_only=unread_only, limit=limit)]
        elif norm == "scheduled_tasks":
            status = q.get("status")
            limit = int(q.get("limit", 50))
            return [t.model_dump() for t in runtime.read.scheduled_tasks(status=status, limit=limit)]
        else:
            raise HTTPException(status_code=404, detail=f"Read endpoint '{name}' not found")

    @app.get("/v1/events", dependencies=[Depends(verify_token)])
    async def stream_events(request: Request) -> StreamingResponse:
        after_param = request.query_params.get("after")
        last_id_hdr = request.headers.get("Last-Event-ID")
        after_id = int(after_param) if after_param is not None else (int(last_id_hdr) if last_id_hdr else None)

        async def event_generator():
            # 1. Replay past events
            if after_id is not None:
                past_events = await asyncio.to_thread(runtime.event_log.since, after_id=after_id)
                for pe in past_events:
                    payload_json = json.dumps(pe.payload, default=str)
                    yield f"id: {pe.id}\nevent: {pe.type}\ndata: {payload_json}\n\n"

            # 2. Live event bus stream
            sub = runtime.bus.subscribe()
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.to_thread(sub.get, timeout=15.0)
                        payload_json = json.dumps(event.payload, default=str)
                        yield f"id: {event.id}\nevent: {event.type}\ndata: {payload_json}\n\n"
                    except Empty:
                        yield ": ping\n\n"
            finally:
                sub.unsubscribe()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    return app
