"""Command handlers for the single-writer runtime."""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING, Any

from runtime.commands import (
    AddDossierNote,
    AddWatchlist,
    ApproveOrder,
    BridgeActionDecide,
    BridgeArchiveConversation,
    BridgeRenameConversation,
    BridgeSay,
    BridgeStop,
    ClosePosition,
    CommandResult,
    DecideProposal,
    EnqueueTask,
    Halt,
    IngestAlert,
    MarkBriefingSeen,
    MarkInboxRead,
    ModifyExit,
    ReconcileBroker,
    RefreshData,
    RejectOrder,
    RemoveWatchlist,
    Resume,
    Say,
    StrikeAnnotation,
    UpdateRiskLimits,
    UpsertAnnotation,
)
from workflows.scheduling import TaskSource

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from runtime.core import RuntimeContext


def handle_enqueue_task(ctx: RuntimeContext, cmd: EnqueueTask, actor: str) -> CommandResult:
    ticker = cmd.ticker.upper().strip()
    agent = cmd.agent.strip()
    reason = cmd.reason.strip()
    when_ts = cmd.when_ts.strip() if cmd.when_ts else ctx.office.get_now_iso()

    with ctx.office.db.transaction():
        task_id = ctx.office.db.enqueue_scheduled_task(
            agent=agent,
            chat=ticker,
            when_ts=when_ts,
            source=TaskSource.MANUAL.value,
            reason=reason,
            data={"ticker": ticker, "manual": True},
        )

        ctx.event_log.append(
            type="task.enqueued",
            subject=f"task:{task_id}",
            payload={
                "task_id": task_id,
                "agent": agent,
                "ticker": ticker,
                "reason": reason,
                "when_ts": when_ts,
            },
            actor=actor,
        )

    return CommandResult(ok=True, data={"task_id": task_id, "due": when_ts})


def handle_say(ctx: RuntimeContext, cmd: Say, actor: str) -> CommandResult:
    agent = cmd.agent.strip()
    chat = cmd.chat.strip()
    text = cmd.text.strip()
    now_iso = ctx.office.get_now_iso()

    data: dict[str, Any] = {}
    with ctx.office.db.transaction():
        chat_id = ctx.office.db.get_or_create_chat(agent, chat)
        msg_id = ctx.office.db.append_message(
            chat_id=chat_id,
            author="user",
            text=text,
            kind="original",
            ts=now_iso,
        )

        ctx.event_log.append(
            type="message.appended",
            subject=f"chat:{chat_id}",
            payload={
                "chat_id": chat_id,
                "message_id": msg_id,
                "agent": agent,
                "topic": chat,
                "text": text,
            },
            actor=actor,
        )
        data = {"message_id": msg_id, "chat_id": chat_id}

        # Business rule: a message to PM enqueues a Scheduled task
        if ctx.office._is_pm_agent(agent):
            task_id = ctx.office.db.enqueue_scheduled_task(
                agent="portfolio_manager",
                chat=chat.upper(),
                when_ts=now_iso,
                source=TaskSource.MANUAL.value,
                reason=text,
                data={"ticker": chat.upper(), "from_user_say": True},
            )
            ctx.event_log.append(
                type="task.enqueued",
                subject=f"task:{task_id}",
                payload={
                    "task_id": task_id,
                    "agent": "portfolio_manager",
                    "ticker": chat.upper(),
                    "reason": text,
                },
                actor=actor,
            )
            data["task_id"] = task_id

    return CommandResult(ok=True, data=data)


def handle_add_dossier_note(ctx: RuntimeContext, cmd: AddDossierNote, actor: str) -> CommandResult:
    from uuid import uuid4

    text = cmd.text.strip()
    if not text:
        return CommandResult(ok=False, reasons=["Note text is required"])
    ticker = cmd.ticker.upper()
    ts = ctx.office.get_now_iso()
    note = {"id": str(uuid4()), "author": actor, "text": text, "ts": ts}
    version = ctx.office.db.write_dossier_section(ticker, "notes", note, actor, ts)
    return CommandResult(ok=True, data={"ticker": ticker, "version": version, "note": note})

def handle_decide_proposal(ctx: RuntimeContext, cmd: DecideProposal, actor: str) -> CommandResult:
    if not cmd.confirm:
        return CommandResult(ok=False, reasons=["decide_proposal requires confirm: true"])
    try:
        env = ctx.office.get_env(None)
        if cmd.action == "accept":
            with ctx.office.db.transaction():
                proposal = ctx.office.db.connection.execute("SELECT * FROM proposals WHERE id = ?", (cmd.proposal_id,)).fetchone()
                if not proposal or ctx.office.db.get_active_cycle(proposal["ticker"]) is not None:
                    raise ValueError("Cannot accept an unknown proposal or while its ticker cycle is active")
                res = env.decide_proposal(cmd.proposal_id, cmd.action, cmd.reason, cmd.when, actor)
                ctx.office.db.connection.execute("UPDATE proposals SET status='processing' WHERE id=?", (cmd.proposal_id,))
        else:
            res = env.decide_proposal(cmd.proposal_id, cmd.action, cmd.reason, cmd.when, actor)
        if cmd.action != "accept":
            return CommandResult(ok=True, data=res)
        row = ctx.office.db.connection.execute("SELECT * FROM proposals WHERE id=?", (cmd.proposal_id,)).fetchone()
        ticker = row["ticker"]
        from workflows.cycle import CycleRunner

        runner = CycleRunner(db=ctx.office.db, backend=ctx.office.backend, env=env,
            order_flow=ctx.office.order_flow, clock=ctx.office.clock, settings=ctx.office.settings,
            registry=ctx.office.registry, ticker=ticker, cycle_id=row["cycle_id"] or 0,
            sleep_fn=ctx.office.sleep_fn, event_log=ctx.office.event_log)
        outcome = runner._process_order_flow(row["direction"], {"draft": env.current_draft(ticker).get("draft")})
        runner._ensure_future_scheduled_task()
        if outcome.is_submitted or outcome.is_pending or outcome.is_queued:
            ctx.office.db.connection.execute("UPDATE proposals SET status='accepted' WHERE id=? AND status='processing'", (cmd.proposal_id,))
            ctx.office.db.write_dossier_section(ticker, "risk", {"verdict": "approved", "rationale": "Risk Gate superato", "guardrails": []}, "risk_gate", ctx.office.get_now_iso())
            return CommandResult(ok=True, data={**res, "order_id": outcome.order_id})
        reason = "; ".join(outcome.reasons) or outcome.status
        ctx.office.db.connection.execute("UPDATE proposals SET status='deferred' WHERE id=? AND status='processing'", (cmd.proposal_id,))
        ctx.office.db.write_dossier_section(ticker, "status", "monitoring", "risk_gate", ctx.office.get_now_iso())
        ctx.office.db.write_dossier_section(ticker, "risk", {"verdict": "declined", "rationale": reason,
            "guardrails": []}, "risk_gate", ctx.office.get_now_iso())
        return CommandResult(ok=False, reasons=[reason])
    except Exception as exc:
        if cmd.action == "accept":
            ctx.office.db.connection.execute("UPDATE proposals SET status='deferred' WHERE id=? AND status='processing'", (cmd.proposal_id,))
        return CommandResult(ok=False, reasons=[str(exc)])


def handle_add_watchlist(ctx: RuntimeContext, cmd: AddWatchlist, actor: str) -> CommandResult:
    ticker = cmd.ticker.upper().strip()
    note = cmd.note or ""
    with ctx.office.db.transaction():
        ctx.office.db.add_watchlist(ticker, note=note, added_by=actor)

        ctx.event_log.append(
            type="watchlist.changed",
            subject=f"ticker:{ticker}",
            payload={"action": "add", "ticker": ticker, "note": note},
            actor=actor,
        )

    return CommandResult(ok=True, data={"ticker": ticker})


def handle_remove_watchlist(ctx: RuntimeContext, cmd: RemoveWatchlist, actor: str) -> CommandResult:
    ticker = cmd.ticker.upper().strip()
    with ctx.office.db.transaction():
        ok = ctx.office.db.remove_watchlist(ticker)

        if ok:
            ctx.event_log.append(
                type="watchlist.changed",
                subject=f"ticker:{ticker}",
                payload={"action": "remove", "ticker": ticker},
                actor=actor,
            )

    return CommandResult(ok=ok, data={"ticker": ticker})


def handle_upsert_annotation(
    ctx: RuntimeContext, cmd: UpsertAnnotation, actor: str
) -> CommandResult:
    conn = ctx.office.db.connection
    existing = conn.execute("SELECT * FROM chart_annotations WHERE id = ?", (cmd.id,)).fetchone()
    if existing and existing["status"] == "struck":
        return CommandResult(ok=False, reasons=["Annotation is struck"])
    ticker = cmd.ticker.strip().upper()
    if existing and existing["ticker"] == ticker and existing["timeframe"] == cmd.timeframe and json.loads(existing["drawing_json"]) == cmd.drawing:
        return CommandResult(ok=True, data={"id": cmd.id})
    now = ctx.office.get_now_iso()
    conn.execute(
        """INSERT INTO chart_annotations (id, ticker, timeframe, drawing_json, author, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET
        ticker=excluded.ticker, timeframe=excluded.timeframe, drawing_json=excluded.drawing_json,
        updated_at=excluded.updated_at""",
        (cmd.id, ticker, cmd.timeframe, json.dumps(cmd.drawing), actor, now, now),
    )
    ctx.event_log.append(
        type="annotation.updated" if existing else "annotation.created",
        subject=f"annotation:{cmd.id}",
        payload={"id": cmd.id, "ticker": ticker},
        actor=actor,
    )
    return CommandResult(ok=True, data={"id": cmd.id})


def handle_strike_annotation(
    ctx: RuntimeContext, cmd: StrikeAnnotation, actor: str
) -> CommandResult:
    conn = ctx.office.db.connection
    existing = conn.execute(
        "SELECT ticker, status FROM chart_annotations WHERE id = ?", (cmd.id,)
    ).fetchone()
    if not existing:
        return CommandResult(ok=False, reasons=["Annotation not found"])
    if existing["status"] == "active":
        now = ctx.office.get_now_iso()
        conn.execute(
            "UPDATE chart_annotations SET status='struck', struck_by=?, struck_at=?, updated_at=? WHERE id=?",
            (actor, now, now, cmd.id),
        )
        ctx.event_log.append(
            type="annotation.struck",
            subject=f"annotation:{cmd.id}",
            payload={"id": cmd.id, "ticker": existing["ticker"]},
            actor=actor,
        )
    return CommandResult(ok=True, data={"id": cmd.id})


def handle_approve_order(ctx: RuntimeContext, cmd: ApproveOrder, actor: str) -> CommandResult:
    fresh_ctx = ctx.office.build_risk_gate_context()
    outcome = ctx.office.order_flow.approve(cmd.order_id, ctx=fresh_ctx)
    if outcome.status in ("submitted", "approved"):
        return CommandResult(
            ok=True,
            data={"order_id": cmd.order_id, "status": outcome.status, "reasons": outcome.reasons},
        )
    else:
        return CommandResult(
            ok=False,
            data={"order_id": cmd.order_id, "status": outcome.status},
            reasons=outcome.reasons,
        )


def handle_reject_order(ctx: RuntimeContext, cmd: RejectOrder, actor: str) -> CommandResult:
    outcome = ctx.office.order_flow.reject(cmd.order_id, reason=cmd.reason)
    return CommandResult(
        ok=True,
        data={"order_id": cmd.order_id, "status": outcome.status, "reasons": outcome.reasons},
    )


def handle_halt(ctx: RuntimeContext, cmd: Halt, actor: str) -> CommandResult:
    ctx.office.halt.halt(cancel_open=cmd.cancel_open)
    return CommandResult(ok=True, data={"halted": True, "cancel_open": cmd.cancel_open})


def handle_resume(ctx: RuntimeContext, cmd: Resume, actor: str) -> CommandResult:
    ctx.office.halt.resume()
    return CommandResult(ok=True, data={"halted": False})


def handle_reconcile_broker(ctx: RuntimeContext, cmd: ReconcileBroker, actor: str) -> CommandResult:
    changed = ctx.office.order_flow.sync_broker_orders()

    env = ctx.office.get_env()
    reader = getattr(ctx.office, "broker_reader", None) or getattr(env, "broker_reader", None)
    acc = reader.get_account() if reader else {}
    positions = reader.get_positions() if reader else ()

    equity = float(acc.get("equity", 0.0) if isinstance(acc, dict) else getattr(acc, "equity", 0.0))
    cash = float(acc.get("cash", 0.0) if isinstance(acc, dict) else getattr(acc, "cash", 0.0))

    now_ts = ctx.office.get_now_iso()
    with ctx.office.db.transaction():
        ctx.office.db.insert_portfolio_snapshot(
            equity=equity,
            cash=cash,
            positions=positions,
            ts=now_ts,
        )

        ctx.event_log.append(
            type="portfolio.synced",
            subject="portfolio",
            payload={
                "ts": now_ts,
                "equity": equity,
                "cash": cash,
                "positions_count": len(positions),
            },
            actor=actor,
        )
        ctx.event_log.append(
            type="portfolio.updated",
            subject="portfolio",
            payload={"reason": "reconcile", "ts": now_ts, "equity": equity, "cash": cash},
            actor=actor,
        )

    return CommandResult(ok=True, data={"orders_synced": len(changed), "portfolio_synced": True})


def handle_refresh_data(ctx: RuntimeContext, cmd: RefreshData, actor: str) -> CommandResult:
    def _run_refresh():
        try:
            result = ctx.office.refresh_data(force=cmd.force, kinds=cmd.kinds) or {}
            with ctx.office.db.transaction():
                ctx.event_log.append(
                    type="data.refreshed",
                    subject="data",
                    payload={"kinds": cmd.kinds, "force": cmd.force, "count": len(result)},
                    actor=actor,
                )
        except Exception as exc:
            logger.exception("Async refresh_data failed: %s", exc)

    thread = threading.Thread(target=_run_refresh, daemon=True, name="refresh-data-worker")
    thread.start()
    return CommandResult(ok=True, data={"status": "accepted", "kinds": cmd.kinds})


def handle_mark_inbox_read(ctx: RuntimeContext, cmd: MarkInboxRead, actor: str) -> CommandResult:
    with ctx.office.db.transaction():
        ctx.office.db.mark_inbox_read(cmd.item_id)
        ctx.event_log.append(
            type="inbox.changed",
            subject=f"inbox:{cmd.item_id}",
            payload={"item_id": cmd.item_id, "read": True},
            actor=actor,
        )
    return CommandResult(ok=True, data={"item_id": cmd.item_id})


def handle_ingest_alert(ctx: RuntimeContext, cmd: IngestAlert, actor: str) -> CommandResult:
    task_id = ctx.office.ingest_external_alert(
        alert_type=cmd.source,
        ticker=cmd.ticker,
        reason=cmd.reason,
        data=cmd.data,
    )
    with ctx.office.db.transaction():
        ctx.event_log.append(
            type="task.enqueued",
            subject=f"task:{task_id}",
            payload={
                "task_id": task_id,
                "ticker": cmd.ticker,
                "source": cmd.source,
                "reason": cmd.reason,
            },
            actor=actor,
        )
    return CommandResult(ok=True, data={"task_id": task_id})


def handle_update_risk_limits(
    ctx: RuntimeContext, cmd: UpdateRiskLimits, actor: str
) -> CommandResult:
    from execution.risk_limits import (
        LimitsValidationError,
        RiskLimitsStore,
        defaults_from_settings,
    )

    store = RiskLimitsStore(ctx.office.db, defaults_from_settings(ctx.office.settings.limits))
    try:
        active = store.update(cmd.limits, cmd.reason, actor)
    except LimitsValidationError as exc:
        return CommandResult(ok=False, reasons=exc.reasons)
    return CommandResult(
        ok=True,
        data={"version": active.version, "limits": active.limits,
              "updated_ts": active.updated_ts, "updated_by": active.updated_by},
    )


def _position_exits(ctx: RuntimeContext) -> Any:
    from execution.position_exits import PositionExits

    office = ctx.office
    return PositionExits(
        office.db,
        office.order_flow.broker,
        office.halt,
        office.order_flow.trade_manager,
        event_log=ctx.event_log,
    )


def _open_trade_and_price(ctx: RuntimeContext, ticker: str) -> tuple[dict | None, Any]:
    from decimal import Decimal

    from runtime import portfolio

    sym = ticker.upper().strip()
    conn = ctx.office.db.connection
    row = conn.execute(
        "SELECT * FROM trades WHERE ticker = ? AND closed_ts IS NULL ORDER BY id DESC LIMIT 1",
        (sym,),
    ).fetchone()
    if row is None:
        return None, None
    trade = dict(row)
    price = portfolio.current_price(conn, sym)
    if price is None:
        price = trade["entry_price"]
    return trade, Decimal(str(price))


def _dec_or_none(value: Any) -> Any:
    from decimal import Decimal

    return Decimal(str(value)) if value is not None else None


def handle_close_position(ctx: RuntimeContext, cmd: ClosePosition, actor: str) -> CommandResult:
    trade, price = _open_trade_and_price(ctx, cmd.ticker)
    if trade is None:
        return CommandResult(ok=False, reasons=[f"Nessuna posizione aperta su {cmd.ticker.upper()}"])
    exits = _position_exits(ctx)
    gate_ctx = ctx.office.build_risk_gate_context()
    qty, limit = _dec_or_none(cmd.qty), _dec_or_none(cmd.limit_price)
    if cmd.dry_run:
        preview = exits.preview_close(trade, qty, cmd.order_type, limit, price, gate_ctx)
        if ctx.office.halt.is_halted():
            preview["risk_gate"] = {"allowed": False, "reasons": [
                "System is halted: all order submissions blocked"]}
        return CommandResult(ok=True, data={"dry_run": True, **preview})
    ok, data, reasons = exits.close(trade, qty, cmd.order_type, limit, price, gate_ctx, actor)
    return CommandResult(ok=ok, data=data, reasons=reasons)


def handle_modify_exit(ctx: RuntimeContext, cmd: ModifyExit, actor: str) -> CommandResult:
    trade, price = _open_trade_and_price(ctx, cmd.ticker)
    if trade is None:
        return CommandResult(ok=False, reasons=[f"Nessuna posizione aperta su {cmd.ticker.upper()}"])
    exits = _position_exits(ctx)
    gate_ctx = ctx.office.build_risk_gate_context()
    stop, target = _dec_or_none(cmd.stop_price), _dec_or_none(cmd.target_price)
    if cmd.dry_run:
        preview = exits.preview_modify(trade, stop, target, price, gate_ctx)
        return CommandResult(ok=True, data={"dry_run": True, **preview})
    ok, data, reasons = exits.modify(trade, stop, target, price, gate_ctx, actor)
    return CommandResult(ok=ok, data=data, reasons=reasons)


# --- Bridge & Briefing Command Handlers ---


def handle_bridge_say(ctx: RuntimeContext, cmd: BridgeSay, actor: str) -> CommandResult:
    now_iso = ctx.office.get_now_iso()
    text = cmd.text.strip()
    conv_id = cmd.conversation_id

    if conv_id is None:
        words = text.split()
        title = " ".join(words[:6])
        if len(words) > 6 or len(title) > 35:
            title = title[:35] + "..."
        conv_id = ctx.office.db.create_bridge_conversation(
            title=title, created_ts=now_iso, status="thinking"
        )
        if ctx.event_log:
            conv = ctx.office.db.get_bridge_conversation(conv_id)
            ctx.event_log.append(
                "bridge.conversation",
                f"bridge_conv:{conv_id}",
                {"conversation": conv},
                actor=actor,
            )
    else:
        conv = ctx.office.db.get_bridge_conversation(conv_id)
        if not conv:
            return CommandResult(ok=False, reasons=[f"Conversation {conv_id} not found"])
        ctx.office.db.update_bridge_conversation(conv_id, status="thinking")

    msg_id = ctx.office.db.append_bridge_message(
        conversation_id=conv_id,
        author="luca",
        kind="text",
        text=text,
        ts=now_iso,
        context=cmd.context,
    )

    if ctx.event_log:
        msg_payload = {
            "id": msg_id,
            "conversation_id": conv_id,
            "author": "luca",
            "kind": "text",
            "text": text,
            "ts": now_iso,
            "context": cmd.context,
            "refs": [],
            "action": None,
        }
        ctx.event_log.append(
            "bridge.message",
            f"bridge_conv:{conv_id}",
            {"conversation_id": conv_id, "message": msg_payload},
            actor=actor,
        )

    if getattr(ctx.runtime, "bridge_runner", None):
        ctx.runtime.bridge_runner.enqueue_turn(conv_id)

    return CommandResult(ok=True, data={"conversation_id": conv_id, "message_id": msg_id})


def handle_bridge_rename_conversation(
    ctx: RuntimeContext, cmd: BridgeRenameConversation, actor: str
) -> CommandResult:
    conv = ctx.office.db.get_bridge_conversation(cmd.conversation_id)
    if not conv:
        return CommandResult(ok=False, reasons=[f"Conversation {cmd.conversation_id} not found"])

    title = cmd.title.strip()
    ctx.office.db.update_bridge_conversation(cmd.conversation_id, title=title)
    if ctx.event_log:
        updated = ctx.office.db.get_bridge_conversation(cmd.conversation_id)
        ctx.event_log.append(
            "bridge.conversation",
            f"bridge_conv:{cmd.conversation_id}",
            {"conversation": updated},
            actor=actor,
        )
    return CommandResult(ok=True, data={"conversation_id": cmd.conversation_id, "title": title})


def handle_bridge_archive_conversation(
    ctx: RuntimeContext, cmd: BridgeArchiveConversation, actor: str
) -> CommandResult:
    conv = ctx.office.db.get_bridge_conversation(cmd.conversation_id)
    if not conv:
        return CommandResult(ok=False, reasons=[f"Conversation {cmd.conversation_id} not found"])

    ctx.office.db.update_bridge_conversation(cmd.conversation_id, archived=cmd.archived)
    if ctx.event_log:
        updated = ctx.office.db.get_bridge_conversation(cmd.conversation_id)
        ctx.event_log.append(
            "bridge.conversation",
            f"bridge_conv:{cmd.conversation_id}",
            {"conversation": updated},
            actor=actor,
        )
    return CommandResult(ok=True, data={"conversation_id": cmd.conversation_id, "archived": cmd.archived})


def handle_bridge_stop(ctx: RuntimeContext, cmd: BridgeStop, actor: str) -> CommandResult:
    stopped = False
    if getattr(ctx.runtime, "bridge_runner", None):
        stopped = ctx.runtime.bridge_runner.request_stop(cmd.conversation_id)
    return CommandResult(ok=True, data={"conversation_id": cmd.conversation_id, "stopped": stopped})


def handle_bridge_action_decide(
    ctx: RuntimeContext, cmd: BridgeActionDecide, actor: str
) -> CommandResult:
    action = ctx.office.db.get_bridge_action(cmd.action_id)
    if not action:
        return CommandResult(ok=False, reasons=[f"Action {cmd.action_id} not found"])

    if action["status"] != "pending":
        return CommandResult(
            ok=False,
            reasons=[f"Action {cmd.action_id} is not pending (status: '{action['status']}')"],
        )

    conv_id = int(action["conversation_id"])
    now_iso = ctx.office.get_now_iso()

    if cmd.decision == "dismiss":
        ctx.office.db.update_bridge_action(
            action_id=cmd.action_id,
            status="dismissed",
            decided_ts=now_iso,
            decided_by=actor,
        )
        if ctx.event_log:
            act_obj = ctx.office.db.get_bridge_action(cmd.action_id)
            ctx.event_log.append(
                "bridge.action",
                f"bridge_action:{cmd.action_id}",
                {"conversation_id": conv_id, "action": act_obj},
                actor=actor,
            )

        dismiss_msg = f"Azione '{action['summary']}' respinta da {actor}."
        msg_id = ctx.office.db.append_bridge_message(
            conversation_id=conv_id,
            author="bridge",
            kind="text",
            text=dismiss_msg,
            ts=now_iso,
        )
        if ctx.event_log:
            ctx.event_log.append(
                "bridge.message",
                f"bridge_conv:{conv_id}",
                {
                    "conversation_id": conv_id,
                    "message": {
                        "id": msg_id,
                        "conversation_id": conv_id,
                        "author": "bridge",
                        "kind": "text",
                        "text": dismiss_msg,
                        "ts": now_iso,
                        "context": None,
                        "refs": [],
                        "action": None,
                    },
                },
                actor="bridge",
            )
        return CommandResult(ok=True, data={"action_id": cmd.action_id, "status": "dismissed"})

    # decision == "confirm"
    from tools.bridge_tools import CAPITAL_COMMAND_MODELS

    cmd_name = action["command"]
    cmd_cls = CAPITAL_COMMAND_MODELS.get(cmd_name)
    if not cmd_cls:
        return CommandResult(ok=False, reasons=[f"Unknown capital command '{cmd_name}'"])

    raw_payload = action.get("payload_json") or action.get("payload") or "{}"
    payload = json.loads(raw_payload) if isinstance(raw_payload, str) else dict(raw_payload)
    if "confirm" in cmd_cls.model_fields:
        payload["confirm"] = True
    if "dry_run" in cmd_cls.model_fields:
        payload["dry_run"] = False

    try:
        orig_cmd = cmd_cls.model_validate(payload)
    except Exception as exc:
        err_msg = f"Invalid payload for {cmd_name}: {exc}"
        ctx.office.db.update_bridge_action(
            action_id=cmd.action_id,
            status="failed",
            result_reasons=[err_msg],
            decided_ts=now_iso,
            decided_by=actor,
        )
        return CommandResult(ok=False, reasons=[err_msg])

    # Execute from same handler via runtime with actor='luca'
    exec_res = ctx.runtime.execute(orig_cmd, actor="luca")

    if exec_res.ok:
        ctx.office.db.update_bridge_action(
            action_id=cmd.action_id,
            status="executed",
            result_reasons=[],
            decided_ts=now_iso,
            decided_by=actor,
        )
        if ctx.event_log:
            act_obj = ctx.office.db.get_bridge_action(cmd.action_id)
            ctx.event_log.append(
                "bridge.action",
                f"bridge_action:{cmd.action_id}",
                {"conversation_id": conv_id, "action": act_obj},
                actor=actor,
            )

        confirm_msg = f"Azione '{action['summary']}' eseguita con successo."
        msg_id = ctx.office.db.append_bridge_message(
            conversation_id=conv_id,
            author="bridge",
            kind="text",
            text=confirm_msg,
            ts=now_iso,
        )
        if ctx.event_log:
            ctx.event_log.append(
                "bridge.message",
                f"bridge_conv:{conv_id}",
                {
                    "conversation_id": conv_id,
                    "message": {
                        "id": msg_id,
                        "conversation_id": conv_id,
                        "author": "bridge",
                        "kind": "text",
                        "text": confirm_msg,
                        "ts": now_iso,
                        "context": None,
                        "refs": [],
                        "action": None,
                    },
                },
                actor="bridge",
            )
        if getattr(ctx.runtime, "bridge_runner", None):
            ctx.runtime.bridge_runner.enqueue_turn(conv_id)

        return CommandResult(
            ok=True,
            data={"action_id": cmd.action_id, "status": "executed", "result": exec_res.data},
        )
    else:
        ctx.office.db.update_bridge_action(
            action_id=cmd.action_id,
            status="failed",
            result_reasons=exec_res.reasons,
            decided_ts=now_iso,
            decided_by=actor,
        )
        if ctx.event_log:
            act_obj = ctx.office.db.get_bridge_action(cmd.action_id)
            ctx.event_log.append(
                "bridge.action",
                f"bridge_action:{cmd.action_id}",
                {"conversation_id": conv_id, "action": act_obj},
                actor=actor,
            )

        fail_msg = f"Esecuzione fallita per l'azione '{action['summary']}': {', '.join(exec_res.reasons)}."
        msg_id = ctx.office.db.append_bridge_message(
            conversation_id=conv_id,
            author="bridge",
            kind="error",
            text=fail_msg,
            ts=now_iso,
        )
        if ctx.event_log:
            ctx.event_log.append(
                "bridge.message",
                f"bridge_conv:{conv_id}",
                {
                    "conversation_id": conv_id,
                    "message": {
                        "id": msg_id,
                        "conversation_id": conv_id,
                        "author": "bridge",
                        "kind": "error",
                        "text": fail_msg,
                        "ts": now_iso,
                        "context": None,
                        "refs": [],
                        "action": None,
                    },
                },
                actor="bridge",
            )
        if getattr(ctx.runtime, "bridge_runner", None):
            ctx.runtime.bridge_runner.enqueue_turn(conv_id)

        return CommandResult(
            ok=False,
            data={"action_id": cmd.action_id, "status": "failed"},
            reasons=exec_res.reasons,
        )


def handle_mark_briefing_seen(
    ctx: RuntimeContext, cmd: MarkBriefingSeen, actor: str
) -> CommandResult:
    seen_ts = ctx.office.db.set_briefing_seen(cmd.ts)
    if ctx.event_log:
        ctx.event_log.append(
            "briefing.updated",
            f"briefing:{seen_ts}",
            {"since": seen_ts},
            actor=actor,
        )
    return CommandResult(ok=True, data={"since": seen_ts})

