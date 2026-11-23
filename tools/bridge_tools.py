"""Tool specifications and implementations for the Bridge Agent."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agents.backend import ToolSpec
from runtime.commands import (
    AddDossierNote,
    AddWatchlist,
    ApproveOrder,
    ClosePosition,
    DecideProposal,
    EnqueueTask,
    Halt,
    MarkInboxRead,
    ModifyExit,
    RefreshData,
    RejectOrder,
    RemoveWatchlist,
    Resume,
    UpdateRiskLimits,
    UpsertAnnotation,
)
from runtime.handlers import (
    handle_add_dossier_note,
    handle_add_watchlist,
    handle_enqueue_task,
    handle_mark_inbox_read,
    handle_refresh_data,
    handle_remove_watchlist,
    handle_strike_annotation,
    handle_upsert_annotation,
)
from tools import schemas
from workflows.scheduling import TaskSource

if TYPE_CHECKING:
    from runtime.core import Runtime

logger = logging.getLogger(__name__)

CAPITAL_COMMAND_MODELS = {
    "approve_order": ApproveOrder,
    "reject_order": RejectOrder,
    "close_position": ClosePosition,
    "modify_exit": ModifyExit,
    "decide_proposal": DecideProposal,
    "halt": Halt,
    "resume": Resume,
    "update_risk_limits": UpdateRiskLimits,
}


def _serialize(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return _serialize(obj.model_dump())
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def build_bridge_tools(
    runtime: Runtime,
    conversation_id: int,
    on_action_proposed: Callable[[int], None] | None = None,
) -> list[ToolSpec]:
    """Build the complete, validated tool catalog for the Bridge Agent in a conversation."""
    db = runtime.office.db
    read = runtime.read
    tools: list[ToolSpec] = []

    def make_tool(
        name: str,
        description: str,
        input_model: type[schemas.BaseModel],
        handler: Callable[..., Any],
    ) -> ToolSpec:
        def wrapped(**kwargs: Any) -> Any:
            started = time.monotonic()
            now_iso = runtime.office.get_now_iso()
            if getattr(db, "event_log", None):
                db.event_log.append(
                    "tool.started",
                    f"tool:bridge:{name}",
                    {
                        "agent": "bridge",
                        "tool": name,
                        "conversation_id": conversation_id,
                        "params": _serialize(kwargs),
                        "ts": now_iso,
                    },
                    actor="bridge",
                )
            try:
                res = handler(**kwargs)
                dur = int((time.monotonic() - started) * 1000)
                db.log_tool_call(
                    agent="bridge",
                    tool=name,
                    params=_serialize(kwargs),
                    result=_serialize(res),
                    error=None,
                    chat_id=None,
                    ts=now_iso,
                    duration_ms=dur,
                )
                if getattr(db, "event_log", None):
                    db.event_log.append(
                        "tool.finished",
                        f"tool:bridge:{name}",
                        {
                            "agent": "bridge",
                            "tool": name,
                            "conversation_id": conversation_id,
                            "duration_ms": dur,
                            "success": True,
                            "error": None,
                            "ts": now_iso,
                        },
                        actor="bridge",
                    )
                return res
            except Exception as exc:
                err_msg = str(exc)
                dur = int((time.monotonic() - started) * 1000)
                db.log_tool_call(
                    agent="bridge",
                    tool=name,
                    params=_serialize(kwargs),
                    result={},
                    error=err_msg,
                    chat_id=None,
                    ts=now_iso,
                    duration_ms=dur,
                )
                if getattr(db, "event_log", None):
                    db.event_log.append(
                        "tool.finished",
                        f"tool:bridge:{name}",
                        {
                            "agent": "bridge",
                            "tool": name,
                            "conversation_id": conversation_id,
                            "duration_ms": dur,
                            "success": False,
                            "error": err_msg,
                            "ts": now_iso,
                        },
                        actor="bridge",
                    )
                raise

        return ToolSpec(
            name=name,
            description=description,
            input_model=input_model,
            fn=wrapped,
        )

    # -------------------------------------------------------------------------
    # 1. READ TOOLS (Compact outputs)
    # -------------------------------------------------------------------------

    def h_read_portfolio() -> dict[str, Any]:
        p = read.portfolio()
        if not p:
            return {"status": "empty", "equity": 0.0, "cash": 0.0, "positions": []}
        return {
            "account_equity": p.equity,
            "cash": p.cash,
            "unrealized_pnl": p.unrealized_pnl,
            "realized_pnl_today": p.realized_pnl_today,
            "positions_count": len(p.positions),
            "positions": [
                {
                    "ticker": pos.ticker,
                    "qty": pos.qty,
                    "avg_entry": pos.entry_price,
                    "current_price": pos.current_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "weight": pos.weight_fraction,
                }
                for pos in p.positions
            ],
        }

    tools.append(
        make_tool(
            "read_portfolio",
            "Read current portfolio equity, cash, unrealized/realized P&L, and open positions.",
            schemas.EmptyBridgeInput,
            h_read_portfolio,
        )
    )

    def h_read_orders(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        orders = read.orders(status=status, limit=limit)
        return [
            {
                "id": o.id,
                "ticker": o.ticker,
                "action": o.action,
                "order_type": o.order_type,
                "qty": o.qty,
                "limit_price": o.limit_price,
                "status": o.status,
                "submitted_at": o.submitted_at,
            }
            for o in orders
        ]

    tools.append(
        make_tool(
            "read_orders",
            "Read recent orders with status filter (e.g. pending_approval, open, filled, rejected).",
            schemas.ReadOrdersInput,
            h_read_orders,
        )
    )

    def h_read_trades(
        status: str | None = None, ticker: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        trades = read.trades(status=status, ticker=ticker, limit=limit)
        return [
            {
                "id": t.id,
                "ticker": t.ticker,
                "status": t.status,
                "opened_ts": t.opened_ts,
                "closed_ts": t.closed_ts,
                "qty": t.qty,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl": t.pnl,
                "r_multiple": t.r_multiple,
            }
            for t in trades
        ]

    tools.append(
        make_tool(
            "read_trades",
            "Read trade history and execution logs with optional status and ticker filter.",
            schemas.ReadTradesInput,
            h_read_trades,
        )
    )

    def h_read_performance() -> dict[str, Any]:
        return {
            "portfolio": _serialize(read.portfolio()),
            "risk_limits": read.risk_limits(),
        }

    tools.append(
        make_tool(
            "read_performance",
            "Read portfolio performance summary and risk limit utilization.",
            schemas.EmptyBridgeInput,
            h_read_performance,
        )
    )

    def h_read_risk_limits() -> dict[str, Any]:
        return {
            "active": read.risk_limits(),
            "versions": read.risk_limits_history(limit=5),
        }

    tools.append(
        make_tool(
            "read_risk_limits",
            "Read active risk limits and recent risk limit revision history.",
            schemas.EmptyBridgeInput,
            h_read_risk_limits,
        )
    )

    def h_read_dossier(ticker: str) -> dict[str, Any]:
        sym = ticker.upper().strip()
        dos = read.dossier(sym)
        return dos if dos else {"ticker": sym, "status": "no_dossier_found"}

    tools.append(
        make_tool(
            "read_dossier",
            "Read senior colleague research dossier and notes for a specific ticker.",
            schemas.ReadStateInput,
            h_read_dossier,
        )
    )

    def h_read_proposals(
        status: str | None = "pending", ticker: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return read.proposals(status=status, ticker=ticker, limit=limit)

    tools.append(
        make_tool(
            "read_proposals",
            "Read proposals submitted by ticker desks with optional status and ticker filter.",
            schemas.ReadProposalsInput,
            h_read_proposals,
        )
    )

    def h_read_agents() -> list[dict[str, Any]]:
        return read.agents()

    tools.append(
        make_tool(
            "read_agents",
            "Read list of office agents, their status (working, waiting, idle), current tasks and daily costs.",
            schemas.EmptyBridgeInput,
            h_read_agents,
        )
    )

    def h_read_agent_chat(agent: str, topic: str, limit: int = 50) -> list[dict[str, Any]]:
        msgs = read.chat(agent=agent.strip(), topic=topic.strip(), limit=limit)
        return [
            {
                "id": m.id,
                "author": m.author,
                "kind": m.kind,
                "text": m.text[:500],
                "ts": m.ts,
            }
            for m in msgs
        ]

    tools.append(
        make_tool(
            "read_agent_chat",
            "Read paginated message history from any specialist agent's chat topic.",
            schemas.ReadAgentChatInput,
            h_read_agent_chat,
        )
    )

    def h_read_tool_calls(
        agent: str | None = None, cycle_id: int | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return read.tool_calls(agent=agent, cycle=cycle_id, limit=limit)

    tools.append(
        make_tool(
            "read_tool_calls",
            "Read recent tool invocations and outcomes by agent or cycle.",
            schemas.ReadToolCallsInput,
            h_read_tool_calls,
        )
    )

    def h_read_usage(
        agent: str | None = None, from_ts: str | None = None, to_ts: str | None = None
    ) -> list[dict[str, Any]]:
        return read.usage(agent=agent, from_ts=from_ts, to_ts=to_ts)

    tools.append(
        make_tool(
            "read_usage",
            "Read LLM call token usage, costs and call counts per agent.",
            schemas.ReadUsageInput,
            h_read_usage,
        )
    )

    def h_read_watchlist() -> list[dict[str, Any]]:
        return [w.model_dump() for w in read.watchlist()]

    tools.append(
        make_tool(
            "read_watchlist",
            "Read the current active watchlist tickers, authors, notes and addition timestamps.",
            schemas.EmptyBridgeInput,
            h_read_watchlist,
        )
    )

    def h_read_annotations(ticker: str, include_struck: bool = False) -> list[dict[str, Any]]:
        return read.annotations(ticker=ticker.upper().strip(), include_struck=include_struck)

    tools.append(
        make_tool(
            "read_annotations",
            "Read chart annotations and drawings for a ticker.",
            schemas.ReadAnnotationsInput,
            h_read_annotations,
        )
    )

    def h_read_prices_ohlcv(
        ticker: str, interval: str = "1h", limit: int = 24
    ) -> list[dict[str, Any]]:
        return runtime.office.get_env().market_data.ohlcv(
            ticker.upper().strip(), interval=interval, limit=limit
        )

    tools.append(
        make_tool(
            "read_prices_ohlcv",
            "Read recent OHLCV market price bars for a ticker.",
            schemas.OHLCVInput,
            h_read_prices_ohlcv,
        )
    )

    def h_read_indicators(ticker: str, timeframe: str = "1h") -> dict[str, Any]:
        return runtime.office.get_env().indicators(ticker.upper().strip(), timeframe=timeframe)

    tools.append(
        make_tool(
            "read_indicators",
            "Calculate technical indicators (SMA, EMA, RSI, ATR) for a ticker.",
            schemas.IndicatorsInput,
            h_read_indicators,
        )
    )

    def h_read_inbox() -> list[dict[str, Any]]:
        return [i.model_dump() for i in read.inbox(unread_only=False, limit=50)]

    tools.append(
        make_tool(
            "read_inbox",
            "Read inbox alerts, notifications, and persistent system errors.",
            schemas.EmptyBridgeInput,
            h_read_inbox,
        )
    )

    def h_read_events(limit: int = 50, since_id: int | None = None) -> list[dict[str, Any]]:
        events = runtime.event_log.since(since_id or 0, limit=limit)
        return [
            {
                "id": e.id,
                "type": e.type,
                "subject": e.subject,
                "actor": e.actor,
                "ts": e.ts,
                "payload": e.payload,
            }
            for e in events
        ]

    tools.append(
        make_tool(
            "read_events",
            "Read recent SSE events log (audit trail) across the office.",
            schemas.ReadEventsInput,
            h_read_events,
        )
    )

    def h_read_briefing(since: str | None = None) -> dict[str, Any]:
        return read.briefing(since=since)

    tools.append(
        make_tool(
            "read_briefing",
            "Read the home briefing summary and key office updates since a timestamp.",
            schemas.ReadBriefingInput,
            h_read_briefing,
        )
    )

    # -------------------------------------------------------------------------
    # 2. AGENT MESSAGING (message_agent)
    # -------------------------------------------------------------------------

    def h_message_agent(agent: str, topic: str, text: str) -> dict[str, Any]:
        target_agent = agent.strip().lower()
        topic_name = topic.strip()
        body = text.strip()
        now_iso = runtime.office.get_now_iso()

        with db.transaction():
            chat_id = db.get_or_create_chat(target_agent, topic_name)
            msg_id = db.append_message(
                chat_id=chat_id,
                author="bridge",
                text=f"[Per conto di Luca]\n{body}",
                kind="original",
                ts=now_iso,
            )
            # Subscribe to agent response relay
            db.subscribe_bridge_relay(
                agent=target_agent,
                topic=topic_name,
                conversation_id=conversation_id,
                ts=now_iso,
            )

            # Rule: Message to PM enqueues a Scheduled task
            if runtime.office._is_pm_agent(target_agent):
                task_id = db.enqueue_scheduled_task(
                    agent="portfolio_manager",
                    chat=topic_name.upper(),
                    when_ts=now_iso,
                    source=TaskSource.MANUAL.value,
                    reason=body,
                    data={"ticker": topic_name.upper(), "from_bridge": True},
                )
                if runtime.event_log:
                    runtime.event_log.append(
                        "task.enqueued",
                        f"task:{task_id}",
                        {
                            "task_id": task_id,
                            "agent": "portfolio_manager",
                            "ticker": topic_name.upper(),
                            "reason": body,
                        },
                        actor="bridge",
                    )
            return {
                "status": "delivered",
                "chat_id": chat_id,
                "message_id": msg_id,
                "agent": target_agent,
                "topic": topic_name,
            }

    tools.append(
        make_tool(
            "message_agent",
            "Send a message to an agent on behalf of Luca. Any reply will automatically relay into this conversation.",
            schemas.MessageAgentInput,
            h_message_agent,
        )
    )

    # -------------------------------------------------------------------------
    # 3. ACTIONS WITHOUT CAPITAL (Executed immediately with actor="bridge")
    # -------------------------------------------------------------------------

    def h_add_watchlist(ticker: str, note: str | None = None) -> dict[str, Any]:
        cmd = AddWatchlist(ticker=ticker, note=note)
        res = handle_add_watchlist(runtime._ctx, cmd, actor="bridge")
        return {"ok": res.ok, "data": res.data, "reasons": res.reasons}

    tools.append(
        make_tool(
            "add_watchlist",
            "Add a ticker to the active watchlist.",
            schemas.AddWatchlistInput,
            h_add_watchlist,
        )
    )

    def h_remove_watchlist(ticker: str) -> dict[str, Any]:
        cmd = RemoveWatchlist(ticker=ticker)
        res = handle_remove_watchlist(runtime._ctx, cmd, actor="bridge")
        return {"ok": res.ok, "data": res.data, "reasons": res.reasons}

    tools.append(
        make_tool(
            "remove_watchlist",
            "Remove a ticker from the active watchlist.",
            schemas.RemoveWatchlistInput,
            h_remove_watchlist,
        )
    )

    def h_add_dossier_note(ticker: str, text: str) -> dict[str, Any]:
        signed_text = f"[Bridge per Luca] {text.strip()}"
        cmd = AddDossierNote(ticker=ticker, text=signed_text)
        res = handle_add_dossier_note(runtime._ctx, cmd, actor="bridge")
        return {"ok": res.ok, "data": res.data, "reasons": res.reasons}

    tools.append(
        make_tool(
            "add_dossier_note",
            "Add an authoritative note to a ticker dossier signed 'Bridge per Luca'.",
            schemas.AddDossierNoteInput,
            h_add_dossier_note,
        )
    )

    def h_enqueue_task(
        agent: str, ticker: str, reason: str, when_ts: str | None = None
    ) -> dict[str, Any]:
        cmd = EnqueueTask(agent=agent, ticker=ticker, reason=reason, when_ts=when_ts)
        res = handle_enqueue_task(runtime._ctx, cmd, actor="bridge")
        return {"ok": res.ok, "data": res.data, "reasons": res.reasons}

    tools.append(
        make_tool(
            "enqueue_task",
            "Enqueue a new Scheduled task for an agent.",
            schemas.EnqueueTaskInput,
            h_enqueue_task,
        )
    )

    def h_refresh_data(kinds: list[str] | None = None, force: bool = False) -> dict[str, Any]:
        cmd = RefreshData(kinds=kinds, force=force)
        res = handle_refresh_data(runtime._ctx, cmd, actor="bridge")
        return {"ok": res.ok, "data": res.data, "reasons": res.reasons}

    tools.append(
        make_tool(
            "refresh_data",
            "Trigger background pre-fetch / refresh of market and portfolio data.",
            schemas.RefreshDataInput,
            h_refresh_data,
        )
    )

    def h_upsert_annotation(
        id: str,
        ticker: str,
        drawing: dict[str, Any],
        timeframe: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        cmd = UpsertAnnotation(
            id=id, ticker=ticker, drawing=drawing, timeframe=timeframe, status=status  # type: ignore[arg-type]
        )
        res = handle_upsert_annotation(runtime._ctx, cmd, actor="bridge")
        return {"ok": res.ok, "data": res.data, "reasons": res.reasons}

    tools.append(
        make_tool(
            "upsert_annotation",
            "Create or update a chart annotation or drawing.",
            schemas.UpsertAnnotationInput,
            h_upsert_annotation,
        )
    )

    def h_strike_annotation(id: str, ticker: str) -> dict[str, Any]:
        from runtime.commands import StrikeAnnotation

        cmd = StrikeAnnotation(id=id, ticker=ticker)
        res = handle_strike_annotation(runtime._ctx, cmd, actor="bridge")
        return {"ok": res.ok, "data": res.data, "reasons": res.reasons}

    tools.append(
        make_tool(
            "strike_annotation",
            "Cross out / strike an existing chart annotation.",
            schemas.StrikeAnnotationInput,
            h_strike_annotation,
        )
    )

    def h_mark_inbox_read(item_id: int) -> dict[str, Any]:
        cmd = MarkInboxRead(item_id=item_id)
        res = handle_mark_inbox_read(runtime._ctx, cmd, actor="bridge")
        return {"ok": res.ok, "data": res.data, "reasons": res.reasons}

    tools.append(
        make_tool(
            "mark_inbox_read",
            "Mark an inbox item as read.",
            schemas.MarkInboxReadInput,
            h_mark_inbox_read,
        )
    )

    # -------------------------------------------------------------------------
    # 4. CAPITAL ACTIONS (ONLY PROPOSED, NEVER DIRECTLY EXECUTED)
    # -------------------------------------------------------------------------

    def h_propose_action(
        command: str, payload: dict[str, Any], summary: str
    ) -> dict[str, Any]:
        cmd_name = command.strip().lower()
        cmd_cls = CAPITAL_COMMAND_MODELS.get(cmd_name)
        if not cmd_cls:
            raise ValueError(
                f"Command '{command}' is not a valid capital-affecting action. "
                f"Valid commands: {sorted(CAPITAL_COMMAND_MODELS.keys())}"
            )

        # 1. Validate payload with Pydantic model
        validated_payload = dict(payload)
        # Enable dry_run or confirm for validation check if required by model
        test_payload = dict(validated_payload)
        if "confirm" in cmd_cls.model_fields:
            test_payload["confirm"] = True
        if "dry_run" in cmd_cls.model_fields:
            test_payload["dry_run"] = True

        try:
            cmd_cls.model_validate(test_payload)
        except Exception as exc:
            raise ValueError(f"Invalid payload for {cmd_name}: {exc}") from exc

        # 2. Run preview / dry-run where available
        preview: dict[str, Any] = {"ok": True, "reasons": [], "detail": {}}
        now_iso = runtime.office.get_now_iso()

        if cmd_name in ("close_position", "modify_exit"):
            dry_cmd = cmd_cls.model_validate({**validated_payload, "dry_run": True, "confirm": False})
            res = runtime.execute(dry_cmd, actor="bridge")
            preview = {
                "ok": res.ok,
                "reasons": res.reasons,
                "detail": res.data,
            }
        elif cmd_name == "approve_order":
            order_id = validated_payload.get("order_id")
            ord_row = db.get_order(int(order_id)) if order_id else None
            if not ord_row:
                preview = {"ok": False, "reasons": [f"Order {order_id} not found"], "detail": {}}
            elif ord_row["status"] != "pending_approval":
                preview = {
                    "ok": False,
                    "reasons": [f"Order {order_id} is '{ord_row['status']}', not 'pending_approval'"],
                    "detail": {},
                }
            elif runtime.office.halt.is_halted():
                preview = {
                    "ok": False,
                    "reasons": ["System is halted: all order submissions blocked"],
                    "detail": {},
                }
            else:
                preview = {"ok": True, "reasons": [], "detail": {"order_id": order_id, "ticker": ord_row["ticker"]}}
        elif cmd_name == "decide_proposal":
            prop_id = validated_payload.get("proposal_id")
            prop = db.connection.execute("SELECT * FROM proposals WHERE id = ?", (prop_id,)).fetchone()
            if not prop:
                preview = {"ok": False, "reasons": [f"Proposal {prop_id} not found"], "detail": {}}
            elif prop["status"] != "pending":
                preview = {"ok": False, "reasons": [f"Proposal {prop_id} is already '{prop['status']}'"], "detail": {}}
            else:
                preview = {"ok": True, "reasons": [], "detail": {"proposal_id": prop_id, "ticker": prop["ticker"]}}

        # 3. Create pending bridge_action in DB
        action_id = db.create_bridge_action(
            conversation_id=conversation_id,
            command=cmd_name,
            payload=validated_payload,
            summary=summary.strip(),
            capital=True,
            status="pending",
            preview=preview,
            created_ts=now_iso,
        )

        action_data = {
            "id": action_id,
            "conversation_id": conversation_id,
            "command": cmd_name,
            "payload": validated_payload,
            "summary": summary.strip(),
            "capital": True,
            "status": "pending",
            "preview": preview,
            "result_reasons": [],
            "decided_ts": None,
            "decided_by": None,
        }

        if getattr(db, "event_log", None):
            db.event_log.append(
                "bridge.action",
                f"bridge_action:{action_id}",
                {"conversation_id": conversation_id, "action": action_data},
                actor="bridge",
            )

        if on_action_proposed is not None:
            on_action_proposed(action_id)

        return action_data

    tools.append(
        make_tool(
            "propose_action",
            "Propose a capital-affecting action (approve/reject order, close position, modify exit, decide proposal, halt, resume, update risk limits). Validates payload, prepares preview, and saves action as pending.",
            schemas.ProposeActionInput,
            h_propose_action,
        )
    )

    return tools
