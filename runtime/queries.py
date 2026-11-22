"""Read model for query operations on the single-writer runtime."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from runtime.core import Runtime


class HealthDTO(BaseModel):
    account_label: str = "default"
    runtime_version: str = "0.1.0"
    halted: bool = False
    broker_stream_connected: bool = False
    broker_configured: bool = False
    next_scheduler_due_ts: str | None = None
    db_size_bytes: int = 0
    last_event_id: int = 0


class PortfolioSnapshotDTO(BaseModel):
    ts: str
    equity: float
    cash: float
    positions: list[dict[str, Any]] = Field(default_factory=list)


class OrderEventDTO(BaseModel):
    id: int
    order_id: int
    ts: str
    event: str
    detail: dict[str, Any] = Field(default_factory=dict)


class OrderDTO(BaseModel):
    id: int
    ticker: str
    side: str
    qty: float
    order_type: str
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    client_order_id: str
    broker_order_id: str | None = None
    status: str
    approval_status: str
    draft_hash: str | None = None
    draft_json: dict[str, Any] = Field(default_factory=dict)
    rejection_reason: str | None = None
    created_ts: str
    updated_ts: str | None = None
    events: list[OrderEventDTO] = Field(default_factory=list)


class TradeDTO(BaseModel):
    id: int
    ticker: str
    entry_order_id: int
    exit_order_id: int | None = None
    entry_price: float
    exit_price: float | None = None
    qty: float
    exit_reason: str | None = None
    opened_ts: str
    closed_ts: str | None = None


class MessageDTO(BaseModel):
    id: int
    chat_id: int
    author: str
    ts: str
    text: str
    kind: str
    cycle_id: int | None = None


class CycleDTO(BaseModel):
    id: int
    ticker: str
    status: str
    opened_ts: str
    closed_ts: str | None = None
    outcome: str | None = None
    budget_used: dict[str, Any] = Field(default_factory=dict)
    messages: list[MessageDTO] = Field(default_factory=list)


class WatchlistItemDTO(BaseModel):
    ticker: str
    added_by: str
    added_ts: str
    note: str | None = None


class InboxItemDTO(BaseModel):
    id: int
    ts: str
    kind: str
    text: str
    read: bool


class ScheduledTaskDTO(BaseModel):
    id: int
    agent: str
    chat: str
    when_ts: str
    source: str
    reason: str
    data: dict[str, Any] = Field(default_factory=dict)
    status: str
    attempts: int
    next_attempt_ts: str | None = None
    merged_into: int | None = None


class ReadModel:
    """Read-only view over the Office SQLite database."""

    def __init__(self, db_path: str | Path, runtime: Runtime | None = None) -> None:
        self.db_path = str(db_path)
        self._runtime = runtime

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._runtime and self._runtime.office:
                return self._runtime.office.db.connection
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            return conn

        # Read-only URI connection
        uri = f"file:{Path(self.db_path).resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def agents(self) -> list[dict[str, Any]]:
        from datetime import UTC, datetime

        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT agent, SUM(tokens_in) AS tokens_in, SUM(tokens_out) AS tokens_out, "
                "SUM(cost) AS cost FROM llm_calls WHERE date(ts) = ? GROUP BY agent",
                (datetime.now(UTC).date().isoformat(),),
            ).fetchall()
            usage = {row['agent']: row for row in rows}
            states = {row['name']: row for row in conn.execute('SELECT * FROM agents')}
            result = []
            for name, config in self._runtime.office.settings.agents.items():
                row = usage.get(name)
                tokens_in = int(row['tokens_in']) if row else 0
                tokens_out = int(row['tokens_out']) if row else 0
                state = states.get(name)
                result.append({
                    'name': name, 'role': name, 'model': config.model,
                    'status': state['status'] if state else 'idle',
                    'current_task': json.loads(state['current_task_json']) if state and state['current_task_json'] else None,
                    'last_activity_ts': state['last_activity_ts'] if state else None,
                    'today_tokens_in': tokens_in, 'today_tokens_out': tokens_out,
                    'today_tokens': tokens_in + tokens_out,
                    'today_cost': float(row['cost']) if row else 0.0,
                })
            return result
        finally:
            if self.db_path != ':memory:':
                conn.close()

    def tool_calls(
        self, agent: str | None = None, cycle: int | None = None,
        after: int = 0, limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            query = ("SELECT t.*, c.topic FROM tool_calls t LEFT JOIN chats c ON c.id = t.chat_id "
                     "WHERE t.id > ?")
            params: list[Any] = [after]
            if agent is not None:
                query += " AND t.agent = ?"
                params.append(agent)
            if cycle is not None:
                query += " AND t.cycle_id = ?"
                params.append(cycle)
            query += " ORDER BY t.id ASC LIMIT ?"
            params.append(limit)
            result = []
            for row in conn.execute(query, params):
                item = dict(row)
                item['params'] = json.loads(item.pop('params_json'))
                item['result'] = json.loads(item.pop('result_json'))
                item['success'] = item['error'] is None
                item['compacted'] = bool(item['compacted'])
                result.append(item)
            return result
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def usage(
        self, agent: str | None = None, from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            query = "SELECT agent, SUM(tokens_in) AS tokens_in, SUM(tokens_out) AS tokens_out, SUM(cost) AS cost, COUNT(*) AS calls FROM llm_calls WHERE 1=1"
            params: list[Any] = []
            if agent is not None:
                query += " AND agent = ?"
                params.append(agent)
            if from_ts is not None:
                query += " AND julianday(ts) >= julianday(?)"
                params.append(from_ts.isoformat())
            if to_ts is not None:
                query += " AND julianday(ts) < julianday(?)"
                params.append(to_ts.isoformat())
            query += " GROUP BY agent ORDER BY agent"
            return [dict(row) for row in conn.execute(query, params)]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def chat_topics(self, agent: str) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT c.id, c.topic, c.created_at, "
                "(SELECT COUNT(*) FROM messages WHERE chat_id = c.id) AS message_count, "
                "m.id AS message_id, m.text, m.author, m.ts, m.cycle_id, cy.ticker "
                "FROM chats c LEFT JOIN messages m ON m.id = "
                "(SELECT id FROM messages WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) "
                "LEFT JOIN cycles cy ON cy.id = m.cycle_id WHERE c.agent = ? "
                "ORDER BY COALESCE(m.ts, c.created_at) DESC, c.id DESC", (agent,),
            ).fetchall()
            return [{
                'id': r['id'], 'topic': r['topic'], 'title': r['topic'],
                'ticker': r['ticker'], 'cycle_id': r['cycle_id'],
                'message_count': r['message_count'],
                'last_activity_ts': r['ts'] or r['created_at'],
                'last_message': {'id': r['message_id'], 'text': r['text'],
                                 'author': r['author'], 'ts': r['ts']} if r['message_id'] else None,
            } for r in rows]
        finally:
            if self.db_path != ':memory:':
                conn.close()

    def health(self) -> HealthDTO:
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()
            last_event_id = int(row[0]) if row else 0

            next_due_row = conn.execute(
                "SELECT MIN(COALESCE(next_attempt_ts, when_ts)) FROM scheduled_tasks WHERE status = 'pending'"
            ).fetchone()
            next_due = next_due_row[0] if next_due_row else None
        finally:
            if self.db_path != ":memory:":
                conn.close()

        halted = False
        db_size = 0
        stream_connected = False
        broker_configured = False

        if self._runtime and self._runtime.office:
            halted = self._runtime.office.halt.is_halted()
            db_size = self._runtime.office.db.db_size_bytes()
            broker_configured = getattr(self._runtime, "broker_configured", False)
            if self._runtime.broker_stream is not None and hasattr(
                self._runtime.broker_stream, "connected"
            ):
                stream_connected = bool(self._runtime.broker_stream.connected)
            elif hasattr(self._runtime, "broker_stream_connected"):
                stream_connected = self._runtime.broker_stream_connected

        return HealthDTO(
            account_label=getattr(self._runtime, "account_label", "default"),
            runtime_version="0.1.0",
            halted=halted,
            broker_stream_connected=stream_connected,
            broker_configured=broker_configured,
            next_scheduler_due_ts=next_due,
            db_size_bytes=db_size,
            last_event_id=last_event_id,
        )

    def portfolio(self) -> PortfolioSnapshotDTO | None:
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT ts, equity, cash, positions_json FROM portfolio_snapshots ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return PortfolioSnapshotDTO(
                ts=str(row["ts"]),
                equity=float(row["equity"]),
                cash=float(row["cash"]),
                positions=json.loads(row["positions_json"]),
            )
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def equity_history(
        self, from_ts: str | None = None, to_ts: str | None = None
    ) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            sql = "SELECT ts, equity, cash FROM portfolio_snapshots WHERE 1=1"
            params: list[Any] = []
            if from_ts:
                sql += " AND ts >= ?"
                params.append(from_ts)
            if to_ts:
                sql += " AND ts <= ?"
                params.append(to_ts)
            sql += " ORDER BY ts ASC"
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def orders(self, status: str | None = None, limit: int = 50) -> list[OrderDTO]:
        conn = self._get_connection()
        try:
            query = "SELECT * FROM orders WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND (status = ? OR approval_status = ?)"
                params.extend([status, status])
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            orders = []
            for r in rows:
                draft_data = {}
                if r["draft_json"]:
                    try:
                        draft_data = json.loads(r["draft_json"])
                    except Exception:
                        pass
                orders.append(
                    OrderDTO(
                        id=int(r["id"]),
                        ticker=str(r["ticker"]),
                        side=str(r["side"]),
                        qty=float(draft_data.get("qty") or 0.0),
                        order_type=str(draft_data.get("order_type") or "bracket"),
                        limit_price=float(draft_data["limit_price"])
                        if draft_data.get("limit_price") is not None
                        else None,
                        stop_loss=float(draft_data["stop_loss"])
                        if draft_data.get("stop_loss") is not None
                        else None,
                        take_profit=float(draft_data["take_profit"])
                        if draft_data.get("take_profit") is not None
                        else None,
                        client_order_id=str(r["client_order_id"]),
                        broker_order_id=r["broker_order_id"],
                        status=str(r["status"]),
                        approval_status=str(r["approval_status"]),
                        draft_hash=r["draft_hash"],
                        draft_json=draft_data,
                        created_ts=str(r["created_ts"]),
                    )
                )
            return orders
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def order(self, order_id: int) -> OrderDTO | None:
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if not row:
                return None
            event_rows = conn.execute(
                "SELECT * FROM order_events WHERE order_id = ? ORDER BY id ASC", (order_id,)
            ).fetchall()
            events = [
                OrderEventDTO(
                    id=int(er["id"]),
                    order_id=int(er["order_id"]),
                    ts=str(er["ts"]),
                    event=str(er["event"]),
                    detail=json.loads(er["detail_json"]) if er["detail_json"] else {},
                )
                for er in event_rows
            ]

            draft_data = {}
            if row["draft_json"]:
                try:
                    draft_data = json.loads(row["draft_json"])
                except Exception:
                    pass

            return OrderDTO(
                id=int(row["id"]),
                ticker=str(row["ticker"]),
                side=str(row["side"]),
                qty=float(draft_data.get("qty") or 0.0),
                order_type=str(draft_data.get("order_type") or "bracket"),
                limit_price=float(draft_data["limit_price"])
                if draft_data.get("limit_price") is not None
                else None,
                stop_loss=float(draft_data["stop_loss"])
                if draft_data.get("stop_loss") is not None
                else None,
                take_profit=float(draft_data["take_profit"])
                if draft_data.get("take_profit") is not None
                else None,
                client_order_id=str(row["client_order_id"]),
                broker_order_id=row["broker_order_id"],
                status=str(row["status"]),
                approval_status=str(row["approval_status"]),
                draft_hash=row["draft_hash"],
                draft_json=draft_data,
                created_ts=str(row["created_ts"]),
                events=events,
            )
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def trades(
        self,
        status: str | None = None,
        ticker: str | None = None,
        limit: int = 50,
    ) -> list[TradeDTO]:
        conn = self._get_connection()
        try:
            query = "SELECT * FROM trades WHERE 1=1"
            params: list[Any] = []
            if ticker:
                query += " AND ticker = ?"
                params.append(ticker.upper().strip())
            if status == "open":
                query += " AND closed_ts IS NULL"
            elif status == "closed":
                query += " AND closed_ts IS NOT NULL"
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [
                TradeDTO(
                    id=int(r["id"]),
                    ticker=str(r["ticker"]),
                    entry_order_id=int(r["entry_order_id"]),
                    exit_order_id=int(r["exit_order_id"])
                    if "exit_order_id" in r.keys() and r["exit_order_id"] is not None
                    else None,
                    entry_price=float(r["entry_price"]),
                    exit_price=float(r["exit_price"]) if r["exit_price"] is not None else None,
                    qty=float(r["qty"]),
                    exit_reason=r["exit_reason"],
                    opened_ts=str(r["opened_ts"]),
                    closed_ts=r["closed_ts"],
                )
                for r in rows
            ]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def cycles(
        self,
        ticker: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[CycleDTO]:
        conn = self._get_connection()
        try:
            query = "SELECT * FROM cycles WHERE 1=1"
            params: list[Any] = []
            if ticker:
                query += " AND ticker = ?"
                params.append(ticker.upper().strip())
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [
                CycleDTO(
                    id=int(r["id"]),
                    ticker=str(r["ticker"]),
                    status=str(r["status"]),
                    opened_ts=str(r["opened_ts"]),
                    closed_ts=r["closed_ts"],
                    outcome=r["outcome"],
                    budget_used=json.loads(r["budget_used_json"]) if r["budget_used_json"] else {},
                )
                for r in rows
            ]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def cycle(self, cycle_id: int) -> CycleDTO | None:
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
            if not row:
                return None
            msg_rows = conn.execute(
                "SELECT * FROM messages WHERE cycle_id = ? ORDER BY id ASC", (cycle_id,)
            ).fetchall()
            messages = [
                MessageDTO(
                    id=int(m["id"]),
                    chat_id=int(m["chat_id"]),
                    author=str(m["author"]),
                    ts=str(m["ts"]),
                    text=str(m["text"]),
                    kind=str(m["kind"]),
                    cycle_id=cycle_id,
                )
                for m in msg_rows
            ]
            return CycleDTO(
                id=int(row["id"]),
                ticker=str(row["ticker"]),
                status=str(row["status"]),
                opened_ts=str(row["opened_ts"]),
                closed_ts=row["closed_ts"],
                outcome=row["outcome"],
                budget_used=json.loads(row["budget_used_json"]) if row["budget_used_json"] else {},
                messages=messages,
            )
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def chat(self, agent: str, topic: str, limit: int = 50) -> list[MessageDTO]:
        conn = self._get_connection()
        try:
            chat_row = conn.execute(
                "SELECT id FROM chats WHERE agent = ? AND topic = ?", (agent, topic)
            ).fetchone()
            if not chat_row:
                return []
            chat_id = int(chat_row["id"])
            rows = conn.execute(
                "SELECT * FROM messages WHERE chat_id = ? ORDER BY id ASC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
            return [
                MessageDTO(
                    id=int(r["id"]),
                    chat_id=chat_id,
                    author=str(r["author"]),
                    ts=str(r["ts"]),
                    text=str(r["text"]),
                    kind=str(r["kind"]),
                    cycle_id=r["cycle_id"],
                )
                for r in rows
            ]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def ticker_state(self, ticker: str) -> dict[str, Any] | None:
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT state_json FROM ticker_state WHERE ticker = ?", (ticker.upper().strip(),)
            ).fetchone()
            if not row or not row["state_json"]:
                return None
            return json.loads(row["state_json"])
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def watchlist(self) -> list[WatchlistItemDTO]:
        conn = self._get_connection()
        try:
            rows = conn.execute("SELECT * FROM watchlist ORDER BY ticker ASC").fetchall()
            return [
                WatchlistItemDTO(
                    ticker=str(r["ticker"]),
                    added_ts=str(r["added_ts"]),
                    added_by=str(r["added_by"]),
                    note=r["note"],
                )
                for r in rows
            ]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def annotations(self, ticker: str, include_struck: bool = False) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM chart_annotations WHERE ticker = ? AND (? OR status = 'active') "
                "ORDER BY created_at, id",
                (ticker.strip().upper(), include_struck),
            )
            result = []
            for row in rows:
                item = dict(row)
                item["drawing"] = json.loads(item.pop("drawing_json"))
                result.append(item)
            return result
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def inbox(self, unread_only: bool = False, limit: int = 50) -> list[InboxItemDTO]:
        conn = self._get_connection()
        try:
            query = "SELECT * FROM inbox WHERE 1=1"
            params: list[Any] = []
            if unread_only:
                query += " AND read = 0"
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [
                InboxItemDTO(
                    id=int(r["id"]),
                    ts=str(r["ts"]),
                    kind=str(r["kind"]),
                    text=str(r["text"]),
                    read=bool(r["read"]),
                )
                for r in rows
            ]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def scheduled_tasks(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[ScheduledTaskDTO]:
        conn = self._get_connection()
        try:
            query = "SELECT * FROM scheduled_tasks WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [
                ScheduledTaskDTO(
                    id=int(r["id"]),
                    agent=str(r["agent"]),
                    chat=str(r["chat"]),
                    when_ts=str(r["when_ts"]),
                    source=str(r["source"]),
                    reason=str(r["reason"]),
                    data=json.loads(r["data_json"]) if r["data_json"] else {},
                    status=str(r["status"]),
                    attempts=int(r["attempts"]),
                    next_attempt_ts=r["next_attempt_ts"],
                    merged_into=r["merged_into"],
                )
                for r in rows
            ]
        finally:
            if self.db_path != ":memory:":
                conn.close()
