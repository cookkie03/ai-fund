"""FastAPI application exposing Command, Read, and Event ports over HTTP and SSE."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from analysis.indicators import (
    average_true_range,
    exponential_moving_average,
    moving_average_convergence_divergence,
    pivot_points,
    relative_strength_index,
    simple_moving_average,
)
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
    StrikeAnnotation,
    UpsertAnnotation,
)

if TYPE_CHECKING:
    from runtime.core import Runtime
    from runtime.events import Event

logger = logging.getLogger(__name__)

_COMMAND_MAP = {
    "enqueue_task": EnqueueTask,
    "say": Say,
    "upsert_annotation": UpsertAnnotation,
    "strike_annotation": StrikeAnnotation,
    "add_watchlist": AddWatchlist,
    "remove_watchlist": RemoveWatchlist,
    "approve_order": ApproveOrder,
    "reject_order": RejectOrder,
    "halt": Halt,
    "resume": Resume,
    "reconcile_broker": ReconcileBroker,
    "refresh_data": RefreshData,
    "mark_inbox_read": MarkInboxRead,
    "ingest_alert": IngestAlert,
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

    def verify_token(request: Request) -> None:
        if token is not None:
            auth = request.headers.get("Authorization")
            if not auth or not auth.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing or invalid Bearer token")
            provided = auth.removeprefix("Bearer ").strip()
            if not hmac.compare_digest(provided, token):
                raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/v1/health", dependencies=[Depends(verify_token)])
    def get_health() -> dict[str, Any]:
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
            raise HTTPException(status_code=422, detail=val_err.errors(include_context=False)) from val_err
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        command_id = request.headers.get("Idempotency-Key")
        actor = request.headers.get("X-Actor", "client")

        res = await asyncio.to_thread(runtime.execute, cmd, actor, command_id)

        if isinstance(cmd, RefreshData):
            return JSONResponse(status_code=202, content=res.model_dump())
        return JSONResponse(status_code=200, content=res.model_dump())

    @app.get("/v1/read/bars", dependencies=[Depends(verify_token)])
    def get_bars(
        ticker: str,
        timeframe: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        timeframe = timeframe if timeframe is not None else runtime.office.settings.market.bar_timeframe
        if not ticker.strip() or not timeframe.strip() or limit < 1 or limit > 10000:
            raise HTTPException(status_code=422, detail="Invalid ticker, timeframe or limit")
        if (start and start.tzinfo is None) or (end and end.tzinfo is None):
            raise HTTPException(status_code=422, detail="Dates must include a timezone")
        if start and end and start > end:
            raise HTTPException(status_code=422, detail="start must precede end")
        rows = runtime.office.get_env().market_data.ohlcv(
            ticker.strip().upper(), interval=timeframe, limit=0
        )
        bars = []
        for row in rows:
            ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            if (start and ts < start) or (end and ts > end):
                continue
            bars.append(
                {
                    "time": int(ts.timestamp()),
                    "open": row["o"],
                    "high": row["h"],
                    "low": row["l"],
                    "close": row["c"],
                    "volume": row["v"],
                }
            )
        return sorted(bars, key=lambda bar: bar["time"])[-limit:]

    @app.get("/v1/read/indicators", dependencies=[Depends(verify_token)])
    def get_indicators(
        ticker: str, names: str = "ema20,rsi14,atr14", timeframe: str | None = None, limit: int = 100,
        start: datetime | None = None, end: datetime | None = None,
    ) -> dict[str, Any]:
        timeframe = timeframe if timeframe is not None else runtime.office.settings.market.bar_timeframe
        selected = get_bars(ticker=ticker, timeframe=timeframe, start=start, end=end, limit=limit)
        bars = get_bars(ticker=ticker, timeframe=timeframe, end=end, limit=10000)
        highs = [Decimal(str(b["high"])) for b in bars]
        lows = [Decimal(str(b["low"])) for b in bars]
        closes = [Decimal(str(b["close"])) for b in bars]
        series = [b["time"] for b in bars]
        out: dict[str, list[float | None]] = {}
        for raw in names.split(","):
            name = raw.strip().lower()
            if not name:
                continue
            match = re.fullmatch(r"(ema|sma|rsi|atr)(\d+)", name)
            if match and not 1 <= int(match.group(2)) <= 10000:
                raise HTTPException(status_code=422, detail="Invalid indicator window")
            if m := re.match(r"^ema(\d+)$", name):
                w = int(m.group(1))
                vals = exponential_moving_average(closes, window=w)
                pad = [None] * (len(closes) - len(vals))
                out[name] = pad + [float(v) for v in vals]
            elif m := re.match(r"^rsi(\d+)$", name):
                w = int(m.group(1))
                vals = relative_strength_index(closes, window=w)
                pad = [None] * (len(closes) - len(vals))
                out[name] = pad + [float(v) for v in vals]
            elif m := re.match(r"^atr(\d+)$", name):
                w = int(m.group(1))
                vals = average_true_range(highs, lows, closes, window=w)
                pad = [None] * (len(closes) - len(vals))
                out[name] = pad + [float(v) for v in vals]
            elif m := re.match(r"^sma(\d+)$", name):
                w = int(m.group(1))
                vals = simple_moving_average(closes, window=w)
                pad = [None] * (len(closes) - len(vals))
                out[name] = pad + [float(v) for v in vals]
            elif name == "macd":
                if len(closes) >= 26:
                    line, sig, hist = moving_average_convergence_divergence(closes)
                    pad_line = [None] * (len(closes) - len(line))
                    pad_sig = [None] * (len(closes) - len(sig))
                    pad_hist = [None] * (len(closes) - len(hist))
                    out["macd_line"] = pad_line + [float(v) for v in line]
                    out["macd_signal"] = pad_sig + [float(v) for v in sig]
                    out["macd_hist"] = pad_hist + [float(v) for v in hist]
                else:
                    out["macd_line"] = [None] * len(closes)
                    out["macd_signal"] = [None] * len(closes)
                    out["macd_hist"] = [None] * len(closes)
            elif name == "pivot":
                if highs and lows and closes:
                    pts = pivot_points(highs, lows, closes)
                    out["pivot_p"] = [float(p[0]) for p in pts]
                    out["pivot_s1"] = [float(p[1]) for p in pts]
                    out["pivot_s2"] = [float(p[2]) for p in pts]
                    out["pivot_r1"] = [float(p[3]) for p in pts]
                    out["pivot_r2"] = [float(p[4]) for p in pts]
                else:
                    for k in ("pivot_p", "pivot_s1", "pivot_s2", "pivot_r1", "pivot_r2"):
                        out[k] = [None] * len(closes)
            else:
                raise HTTPException(status_code=422, detail=f"Indicator '{name}' unsupported")
        selected_times = {bar["time"] for bar in selected}
        indexes = [i for i, ts in enumerate(series) if ts in selected_times]
        return {
            "ticker": ticker.strip().upper(),
            "timeframe": timeframe,
            "series": [series[i] for i in indexes],
            "indicators": {name: [values[i] for i in indexes] for name, values in out.items()},
        }

    @app.get("/v1/read/equity_history", dependencies=[Depends(verify_token)])
    def get_equity_history(
        from_ts: str | None = Query(default=None, alias="from"),
        to_ts: str | None = Query(default=None, alias="to"),
    ) -> list[dict[str, Any]]:
        return runtime.read.equity_history(from_ts=from_ts, to_ts=to_ts)

    @app.get("/v1/read/tool_calls", dependencies=[Depends(verify_token)])
    def get_tool_calls(
        agent: str | None = None, cycle: int | None = Query(default=None, ge=1),
        after: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        return runtime.read.tool_calls(agent=agent, cycle=cycle, after=after, limit=limit)

    @app.get("/v1/read/usage", dependencies=[Depends(verify_token)])
    def get_usage(
        agent: str | None = None,
        from_ts: datetime | None = Query(default=None, alias="from"),  # noqa: B008
        to_ts: datetime | None = Query(default=None, alias="to"),  # noqa: B008
    ) -> list[dict[str, Any]]:
        if (from_ts and from_ts.tzinfo is None) or (to_ts and to_ts.tzinfo is None):
            raise HTTPException(status_code=422, detail="Dates must include a timezone")
        if from_ts and to_ts and from_ts > to_ts:
            raise HTTPException(status_code=422, detail="from must precede to")
        return runtime.read.usage(agent, from_ts, to_ts)

    @app.get("/v1/read/annotations", dependencies=[Depends(verify_token)])
    def get_annotations(ticker: str, include_struck: bool = False) -> list[dict[str, Any]]:
        return runtime.read.annotations(ticker, include_struck)

    @app.get("/v1/read/{name}", dependencies=[Depends(verify_token)])
    def execute_read(name: str, request: Request) -> Any:
        q = request.query_params
        norm = name.lower().replace("-", "_")

        if norm == "agents":
            return runtime.read.agents()
        if norm == "chat_topics":
            agent = q.get("agent", "").strip()
            if not agent:
                raise HTTPException(status_code=422, detail="agent is required")
            return runtime.read.chat_topics(agent)
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
            return [
                t.model_dump()
                for t in runtime.read.trades(status=status, ticker=ticker, limit=limit)
            ]
        elif norm == "cycles":
            ticker = q.get("ticker")
            status = q.get("status")
            limit = int(q.get("limit", 50))
            return [
                c.model_dump()
                for c in runtime.read.cycles(ticker=ticker, status=status, limit=limit)
            ]
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
            return [
                m.model_dump() for m in runtime.read.chat(agent=agent, topic=topic, limit=limit)
            ]
        elif norm == "ticker_state":
            ticker = q.get("ticker", "")
            state = runtime.read.ticker_state(ticker)
            return state or {}
        elif norm == "watchlist":
            return [w.model_dump() for w in runtime.read.watchlist()]
        elif norm == "inbox":
            unread_only = q.get("unread_only", "false").lower() in ("true", "1")
            limit = int(q.get("limit", 50))
            return [
                i.model_dump() for i in runtime.read.inbox(unread_only=unread_only, limit=limit)
            ]
        elif norm == "scheduled_tasks":
            status = q.get("status")
            limit = int(q.get("limit", 50))
            return [
                t.model_dump() for t in runtime.read.scheduled_tasks(status=status, limit=limit)
            ]
        else:
            raise HTTPException(status_code=404, detail=f"Read endpoint '{name}' not found")

    @app.get("/v1/events", dependencies=[Depends(verify_token)])
    async def stream_events(request: Request) -> StreamingResponse:
        after_param = request.query_params.get("after")
        last_id_hdr = request.headers.get("Last-Event-ID")
        after_id = (
            int(after_param)
            if after_param is not None
            else (int(last_id_hdr) if last_id_hdr else None)
        )

        queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=100)
        loop = asyncio.get_running_loop()

        def _on_bus_event(event: Event) -> None:
            def _put():
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Client is too slow: push None sentinel to trigger disconnect and client replay
                    try:
                        queue.put_nowait(None)
                    except asyncio.QueueFull:
                        pass

            loop.call_soon_threadsafe(_put)

        async def event_generator():
            runtime.bus.add_listener(_on_bus_event)
            seen_ids: set[int] = set()
            try:
                # 1. Replay past events
                if after_id is not None:
                    past_events = await asyncio.to_thread(
                        runtime.event_log.since, after_id=after_id
                    )
                    for pe in past_events:
                        seen_ids.add(pe.id)
                        payload_json = json.dumps(pe.payload, default=str)
                        yield f"id: {pe.id}\nevent: {pe.type}\ndata: {payload_json}\n\n"

                # 2. Async queue consumer without blocking threadpool
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        if event is None:
                            # Queue was full: close connection so client reconnects with Last-Event-ID
                            logger.warning(
                                "SSE queue full for client, closing connection to force replay"
                            )
                            break
                        if event.id in seen_ids:
                            continue
                        seen_ids.add(event.id)
                        payload_json = json.dumps(event.payload, default=str)
                        yield f"id: {event.id}\nevent: {event.type}\ndata: {payload_json}\n\n"
                    except TimeoutError:
                        yield ": ping\n\n"
            finally:
                runtime.bus.remove_listener(_on_bus_event)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    return app
