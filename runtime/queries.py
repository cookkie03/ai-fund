"""Read model for query operations on the single-writer runtime."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from execution.risk_limits import (
    ConnRiskLimitsReader,
    RiskLimitsStore,
    bounds_payload,
    defaults_from_settings,
)
from runtime import portfolio

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
    pnl: float | None = None
    r_multiple: float | None = None
    duration_s: float | None = None
    proposed_by: str | None = None
    stop_price: float | None = None
    target_price: float | None = None
    qty_remaining: float | None = None


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

    # --- Portafoglio ---

    def _now(self) -> datetime:
        office = getattr(self._runtime, "office", None)
        try:
            return office.get_now().astimezone(UTC)
        except Exception:
            return datetime.now(UTC)

    def _limits_store(self, conn: sqlite3.Connection) -> RiskLimitsStore:
        office = getattr(self._runtime, "office", None)
        if office is not None:
            defaults = defaults_from_settings(office.settings.limits)
        else:
            from config.office_settings import OfficeSettings

            defaults = defaults_from_settings(OfficeSettings().limits)
        return RiskLimitsStore(ConnRiskLimitsReader(conn), defaults)  # type: ignore[arg-type]

    def _with_conn(self, fn: Any) -> Any:
        conn = self._get_connection()
        try:
            return fn(conn)
        finally:
            if self.db_path != ":memory:":
                conn.close()

    @staticmethod
    def _trade_extras(conn: sqlite3.Connection, r: sqlite3.Row) -> dict[str, Any]:
        keys = r.keys()
        closed = r["closed_ts"] is not None
        pnl = portfolio.trade_pnl(r) if closed and "realized_pnl" in keys else None
        opened = portfolio._parse(r["opened_ts"])
        end = portfolio._parse(r["closed_ts"]) if closed else None
        stop, target = portfolio.trade_levels(conn, r)
        qty = float(r["qty"])
        done = float(r["closed_qty"] or 0.0) if "closed_qty" in keys else 0.0
        return {
            "pnl": pnl,
            "r_multiple": portfolio.trade_r_multiple(r, pnl) if closed else None,
            "duration_s": (end - opened).total_seconds() if opened and end else None,
            "proposed_by": r["proposed_by"] if "proposed_by" in keys else None,
            "stop_price": stop,
            "target_price": target,
            "qty_remaining": None if closed else max(qty - done, 0.0),
        }

    def risk_limits(self) -> dict[str, Any]:
        def run(conn: sqlite3.Connection) -> dict[str, Any]:
            active = self._limits_store(conn).active()
            return {
                "version": active.version,
                "updated_ts": active.updated_ts,
                "updated_by": active.updated_by,
                "limits": active.limits,
                "bounds": bounds_payload(),
                "usage": portfolio.limits_usage(conn, self._now(), active.limits),
            }

        return self._with_conn(run)

    def risk_limits_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._with_conn(lambda conn: self._limits_store(conn).history(limit))

    def portfolio_summary(self) -> dict[str, Any]:
        def run(conn: sqlite3.Connection) -> dict[str, Any]:
            limits = self._limits_store(conn).active().limits
            return portfolio.portfolio_summary(conn, self._now(), limits)

        return self._with_conn(run)

    def positions(self) -> list[dict[str, Any]]:
        return self._with_conn(lambda conn: portfolio.open_positions(conn, self._now()))

    def allocation(self) -> dict[str, Any]:
        def run(conn: sqlite3.Connection) -> dict[str, Any]:
            limits = self._limits_store(conn).active().limits
            return portfolio.allocation(conn, self._now(), limits)

        return self._with_conn(run)

    def performance(self, period: str = "1M", benchmark: str | None = "SPY") -> dict[str, Any]:
        return self._with_conn(
            lambda conn: portfolio.performance(conn, self._now(), period, benchmark)
        )

    def attribution(self, period: str = "1M") -> dict[str, Any]:
        return self._with_conn(lambda conn: portfolio.attribution(conn, self._now(), period))

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
            configs = self._runtime.office.settings.agents
            agent_configs = [(name, config) for name, config in configs.items() if name != "ticker_agent"]
            agent_configs.extend((name, configs["ticker_agent"]) for name in states
                                 if name.startswith("ticker:") and "ticker_agent" in configs)
            for name, config in agent_configs:
                row = usage.get(name)
                tokens_in = int(row['tokens_in']) if row else 0
                tokens_out = int(row['tokens_out']) if row else 0
                state = states.get(name)
                result.append({
                    'name': name, 'role': name, 'model': config.model,
                    'kind': 'ticker' if name.startswith('ticker:') else 'core',
                    'ticker': name.removeprefix('ticker:') if name.startswith('ticker:') else None,
                    'supervisor': 'portfolio_manager' if name.startswith('ticker:') else None,
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
            return portfolio.equity_history_with_drawdown(
                [dict(r) for r in conn.execute(sql, params).fetchall()]
            )
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
                    **self._trade_extras(conn, r),
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
                # Latest `limit` messages, returned oldest-first for display.
                "SELECT * FROM (SELECT * FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?) "
                "ORDER BY id ASC",
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

    def dossier_history(self, ticker: str, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT version, ts, author, sections_json FROM dossier_versions "
                "WHERE ticker = ? ORDER BY version DESC LIMIT ?",
                (ticker.upper().strip(), max(1, min(limit, 500))),
            ).fetchall()
            return [{"version": row["version"], "ts": row["ts"], "author": row["author"],
                     "sections_changed": json.loads(row["sections_json"])} for row in rows]
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def dossier_version(self, ticker: str, version: int) -> dict[str, Any] | None:
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT document_json FROM dossier_versions WHERE ticker = ? AND version = ?",
                (ticker.upper().strip(), version),
            ).fetchone()
            return json.loads(row["document_json"]) if row else None
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def proposals(self, status: str | None = None, ticker: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            clauses, params = [], []
            if status:
                clauses.append("status = ?")
                params.append(status)
            if ticker:
                clauses.append("ticker = ?")
                params.append(ticker.upper().strip())
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(max(1, min(limit, 500)))
            rows = conn.execute(f"SELECT * FROM proposals {where} ORDER BY id DESC LIMIT ?", params).fetchall()
            result = [dict(row) for row in rows]
            for row in result:
                if row["status"] == "processing":
                    row["status"] = "accepted"
            return result
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def dossier(self, ticker: str) -> dict[str, Any] | None:
        ticker = ticker.upper().strip()
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT document_json FROM dossier_versions WHERE ticker = ? "
                "ORDER BY version DESC LIMIT 1", (ticker,),
            ).fetchone()
            if row is None:
                return None
            document = json.loads(row["document_json"])
            from datetime import UTC, datetime

            thresholds = (self._runtime.office.settings.dossier_stale_days
                          if self._runtime else {"default": 30})
            now = self._runtime.office.get_now() if self._runtime else datetime.now(UTC)
            for item in document.get("desks", []):
                if item.get("status") != "active":
                    continue
                try:
                    reference = datetime.fromisoformat(item["reference_date"].replace("Z", "+00:00"))
                    if reference.tzinfo is None:
                        reference = reference.replace(tzinfo=UTC)
                    threshold = thresholds.get(item.get("section"), thresholds.get("default", 30))
                    if (now - reference).total_seconds() > threshold * 86400:
                        item["status"] = "stale"
                except (KeyError, ValueError, TypeError):
                    item["status"] = "stale"
            security = conn.execute(
                "SELECT name, sector, industry FROM securities WHERE symbol = ?", (ticker,)
            ).fetchone()
            portfolio = self.portfolio()
            positions = portfolio.positions if portfolio else []
            position = next((p for p in positions if str(p.get("symbol", "")).upper() == ticker), None)
            equity = portfolio.equity if portfolio else 0
            cash = portfolio.cash if portfolio else None
            # Same price source as the Portafoglio: latest snapshot, then the last daily close.
            from runtime import portfolio as portfolio_math

            price = portfolio_math.current_price(conn, ticker)
            identity = {"name": security["name"] if security else None,
                        "sector": security["sector"] if security else None,
                        "industry": security["industry"] if security else None,
                        "market_cap": None, "currency": None, "current_price": price,
                        "as_of": ((portfolio_math.latest_snapshot(conn) or {}).get("ts") if price is not None else None)}
            context = {"invested": bool(position), "qty": None, "position_weight": None,
                       "avg_entry_price": None, "unrealized_pnl": None, "sector_exposure": None,
                       "cash_fraction": cash / equity if cash is not None and equity else None}
            if position:
                market_value = position.get("market_value")
                context.update(qty=position.get("qty", position.get("quantity")),
                               position_weight=float(market_value) / equity if market_value is not None and equity else None,
                               avg_entry_price=position.get("avg_entry_price", position.get("average_entry_price")),
                               unrealized_pnl=position.get("unrealized_pl"))
            return {"ticker": ticker, "version": document["version"],
                    "updated_ts": document["updated_ts"], "updated_by": document["updated_by"],
                    "status": document.get("status", "idle"), "identity": identity, "portfolio": context,
                    "desks": document.get("desks", []), "thesis": document.get("thesis"),
                    "proposal": document.get("proposal"), "risk": document.get("risk"),
                    "decisions": document.get("decisions", []), "lessons": document.get("lessons", []),
                    "notes": document.get("notes", []), "stale_count": sum(
                        1 for item in document.get("desks", []) if item.get("status") == "stale")}
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def dossiers(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            rows = conn.execute(
                "SELECT ticker, MAX(version) FROM dossier_versions GROUP BY ticker "
                "ORDER BY MAX(ts) DESC LIMIT ?", (max(1, min(limit, 500)),)
            ).fetchall()
            tickers = [row["ticker"] for row in rows]
        finally:
            if self.db_path != ":memory:":
                conn.close()
        result = []
        for ticker in tickers:
            dossier = self.dossier(ticker)
            if dossier is None:
                continue
            thesis = dossier["thesis"] or {}
            proposal = dossier["proposal"] or {}
            result.append({"ticker": ticker, "status": dossier["status"],
                           "direction": thesis.get("direction"), "conviction": thesis.get("conviction"),
                           "proposal_status": proposal.get("status"), "updated_ts": dossier["updated_ts"],
                           "stale_count": dossier["stale_count"], "invested": dossier["portfolio"]["invested"]})
        return result

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

    # --- Bridge & Briefing Read Endpoints ---

    def bridge_conversations(
        self,
        limit: int = 50,
        q: str | None = None,
        archived: bool | None = False,
    ) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            query = """
                SELECT c.*,
                       (SELECT COUNT(*) FROM bridge_messages m WHERE m.conversation_id = c.id) AS message_count,
                       (SELECT COUNT(*) FROM bridge_actions a WHERE a.conversation_id = c.id AND a.status = 'pending') AS pending_actions
                FROM bridge_conversations c
                WHERE 1=1
            """
            params: list[Any] = []
            if archived is not None:
                query += " AND c.archived = ?"
                params.append(1 if archived else 0)
            if q and q.strip():
                pattern = f"%{q.strip()}%"
                query += " AND (c.title LIKE ? OR EXISTS (SELECT 1 FROM bridge_messages m WHERE m.conversation_id = c.id AND m.text LIKE ?))"
                params.extend([pattern, pattern])
            query += " ORDER BY c.updated_ts DESC, c.id DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            result: list[dict[str, Any]] = []
            for r in rows:
                conv = dict(r)
                conv["archived"] = bool(conv["archived"])
                last_msg_row = conn.execute(
                    "SELECT author, text, ts FROM bridge_messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
                    (conv["id"],),
                ).fetchone()
                conv["last_message"] = dict(last_msg_row) if last_msg_row else None
                result.append(conv)
            return result
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def bridge_conversation(
        self,
        id: int,
        limit: int = 100,
        before: int | None = None,
    ) -> dict[str, Any] | None:
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM bridge_conversations WHERE id = ?", (id,)).fetchone()
            if not row:
                return None
            conv = dict(row)
            conv["archived"] = bool(conv["archived"])

            if before is not None:
                msg_rows = conn.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM bridge_messages
                        WHERE conversation_id = ? AND id < ?
                        ORDER BY id DESC LIMIT ?
                    ) ORDER BY id ASC
                    """,
                    (id, before, limit),
                ).fetchall()
            else:
                msg_rows = conn.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM bridge_messages
                        WHERE conversation_id = ?
                        ORDER BY id DESC LIMIT ?
                    ) ORDER BY id ASC
                    """,
                    (id, limit),
                ).fetchall()

            messages: list[dict[str, Any]] = []
            for mr in msg_rows:
                m = dict(mr)
                m["context"] = json.loads(m["context_json"]) if m.get("context_json") else None
                m["refs"] = json.loads(m["refs_json"]) if m.get("refs_json") else []
                action_id = m.get("action_id")
                action_dict = None
                if action_id:
                    act_row = conn.execute("SELECT * FROM bridge_actions WHERE id = ?", (action_id,)).fetchone()
                    if act_row:
                        action_dict = dict(act_row)
                        action_dict["payload"] = json.loads(action_dict["payload_json"]) if action_dict.get("payload_json") else {}
                        action_dict["preview"] = json.loads(action_dict["preview_json"]) if action_dict.get("preview_json") else None
                        action_dict["result_reasons"] = json.loads(action_dict["result_reasons_json"]) if action_dict.get("result_reasons_json") else []
                        action_dict["capital"] = bool(action_dict["capital"])
                        action_dict.pop("payload_json", None)
                        action_dict.pop("preview_json", None)
                        action_dict.pop("result_reasons_json", None)
                m["action"] = action_dict
                m.pop("context_json", None)
                m.pop("refs_json", None)
                m.pop("action_id", None)
                messages.append(m)

            conv["messages"] = messages
            return conv
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def bridge_actions(
        self,
        status: str | None = None,
        conversation_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        conn = self._get_connection()
        try:
            query = "SELECT * FROM bridge_actions WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if conversation_id is not None:
                query += " AND conversation_id = ?"
                params.append(conversation_id)
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            actions: list[dict[str, Any]] = []
            for r in rows:
                a = dict(r)
                a["payload"] = json.loads(a["payload_json"]) if a.get("payload_json") else {}
                a["preview"] = json.loads(a["preview_json"]) if a.get("preview_json") else None
                a["result_reasons"] = json.loads(a["result_reasons_json"]) if a.get("result_reasons_json") else []
                a["capital"] = bool(a["capital"])
                a.pop("payload_json", None)
                a.pop("preview_json", None)
                a.pop("result_reasons_json", None)
                actions.append(a)
            return actions
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def briefing(self, since: str | None = None) -> dict[str, Any]:
        from datetime import timedelta

        conn = self._get_connection()
        try:
            now_dt = self._now()
            now_iso = now_dt.isoformat().replace("+00:00", "Z")

            if not since:
                row_seen = conn.execute("SELECT value FROM briefing_state WHERE key = 'last_seen_ts'").fetchone()
                if row_seen and row_seen["value"]:
                    since_ts = str(row_seen["value"])
                else:
                    since_ts = (now_dt - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
            else:
                since_ts = since

            # 1. Portfolio stats
            port = self.portfolio()
            portfolio_data = None
            if port:
                val = float(port.equity)
                snap = conn.execute(
                    "SELECT equity FROM portfolio_snapshots WHERE ts <= ? ORDER BY ts DESC LIMIT 1",
                    (since_ts,),
                ).fetchone()
                if snap:
                    base_eq = float(snap["equity"])
                    change = val - base_eq
                    chg_frac = (change / base_eq) if base_eq > 0 else 0.0
                else:
                    change = float(port.realized_pnl_today + port.unrealized_pnl)
                    base = val - change
                    chg_frac = (change / base) if base > 0 else 0.0
                portfolio_data = {
                    "value": round(val, 2),
                    "change": round(change, 2),
                    "change_fraction": round(chg_frac, 4),
                }

            items: list[dict[str, Any]] = []

            # 2. Trades
            trade_rows = conn.execute(
                """
                SELECT id, ticker, CASE WHEN closed_ts IS NULL THEN 'open' ELSE 'closed' END AS status,
                       qty, entry_price, exit_price, realized_pnl, opened_ts, closed_ts
                FROM trades
                WHERE opened_ts >= ? OR (closed_ts IS NOT NULL AND closed_ts >= ?)
                ORDER BY COALESCE(closed_ts, opened_ts) DESC LIMIT 50
                """,
                (since_ts, since_ts),
            ).fetchall()
            for tr in trade_rows:
                ts_val = tr["closed_ts"] or tr["opened_ts"]
                pnl_str = f" P&L: {round(float(tr['realized_pnl']), 2)}" if tr["realized_pnl"] is not None else ""
                items.append({
                    "id": f"trade-{tr['id']}",
                    "type": "trade",
                    "ts": ts_val,
                    "title": f"Trade {tr['ticker']} {tr['status']} ({tr['qty']} @ {tr['entry_price'] or 0}){pnl_str}",
                    "detail": f"Uscita: {tr['exit_price']}" if tr["exit_price"] else None,
                    "ticker": tr["ticker"],
                    "ref": {"type": "trade", "id": int(tr["id"])},
                    "severity": "info",
                })

            # 3. Orders pending approval
            ord_rows = self.orders(status="pending", limit=50)
            for o in ord_rows:
                items.append({
                    "id": f"order-pending-{o.id}",
                    "type": "order_pending",
                    "ts": o.created_ts,
                    "title": f"Ordine in attesa: {o.ticker} {o.side} {o.qty}",
                    "detail": f"{o.order_type} limit {o.limit_price}" if o.limit_price else o.order_type,
                    "ticker": o.ticker,
                    "ref": {"type": "order", "id": int(o.id)},
                    "severity": "attention",
                })

            # 4. Proposals pending
            prop_pending = conn.execute(
                """
                SELECT id, ticker, agent, direction, conviction, submitted_ts, reason
                FROM proposals
                WHERE status = 'pending'
                ORDER BY id DESC LIMIT 50
                """
            ).fetchall()
            for p in prop_pending:
                items.append({
                    "id": f"proposal-pending-{p['id']}",
                    "type": "proposal_pending",
                    "ts": p["submitted_ts"],
                    "title": f"Proposta in attesa: {p['ticker']} ({p['direction']})",
                    "detail": p["reason"],
                    "ticker": p["ticker"],
                    "ref": {"type": "proposal", "id": int(p["id"])},
                    "severity": "attention",
                })

            # 5. Proposals decided
            prop_decided = conn.execute(
                """
                SELECT id, ticker, agent, status, direction, decided_ts, decided_by, reason
                FROM proposals
                WHERE status IN ('accepted', 'rejected', 'deferred') AND decided_ts >= ?
                ORDER BY decided_ts DESC LIMIT 50
                """,
                (since_ts,),
            ).fetchall()
            for p in prop_decided:
                items.append({
                    "id": f"proposal-decided-{p['id']}",
                    "type": "proposal_decided",
                    "ts": p["decided_ts"],
                    "title": f"Proposta {p['ticker']} {p['status']} da {p['decided_by'] or 'PM'}",
                    "detail": p["reason"],
                    "ticker": p["ticker"],
                    "ref": {"type": "proposal", "id": int(p["id"])},
                    "severity": "info",
                })

            # 6. Alerts
            alert_rows = conn.execute(
                """
                SELECT id, text, ts FROM inbox
                WHERE kind = 'alert' AND ts >= ?
                ORDER BY id DESC LIMIT 50
                """,
                (since_ts,),
            ).fetchall()
            for a in alert_rows:
                items.append({
                    "id": f"alert-{a['id']}",
                    "type": "alert",
                    "ts": a["ts"],
                    "title": f"Alert: {a['text'][:80]}",
                    "detail": a["text"],
                    "ticker": None,
                    "ref": None,
                    "severity": "attention",
                })

            # 7. Halt / Resume
            halt_rows = conn.execute(
                """
                SELECT id, payload, ts FROM events
                WHERE type = 'halt.changed' AND ts >= ?
                ORDER BY id DESC LIMIT 50
                """,
                (since_ts,),
            ).fetchall()
            for h in halt_rows:
                payload = json.loads(h["payload"]) if h["payload"] else {}
                status = payload.get("status")
                if status == "halted":
                    items.append({
                        "id": f"halt-{h['id']}",
                        "type": "halt",
                        "ts": h["ts"],
                        "title": "Trading Halt attivato",
                        "detail": payload.get("reason"),
                        "ticker": None,
                        "ref": None,
                        "severity": "critical",
                    })
                elif status == "resumed":
                    items.append({
                        "id": f"resume-{h['id']}",
                        "type": "resume",
                        "ts": h["ts"],
                        "title": "Trading ripreso",
                        "detail": payload.get("reason"),
                        "ticker": None,
                        "ref": None,
                        "severity": "info",
                    })

            # 8. Dossiers
            dos_rows = conn.execute(
                """
                SELECT ticker, version, ts, author FROM dossier_versions
                WHERE ts >= ?
                ORDER BY ts DESC LIMIT 50
                """,
                (since_ts,),
            ).fetchall()
            for d in dos_rows:
                items.append({
                    "id": f"dossier-{d['ticker']}-{d['version']}",
                    "type": "dossier",
                    "ts": d["ts"],
                    "title": f"Scheda {d['ticker']} aggiornata (v{d['version']})",
                    "detail": f"Aggiornata da {d['author']}",
                    "ticker": d["ticker"],
                    "ref": {"type": "ticker", "id": d["ticker"]},
                    "severity": "info",
                })

            # 9. Agent errors
            err_rows = conn.execute(
                """
                SELECT id, text, ts FROM inbox
                WHERE kind = 'error' AND ts >= ?
                ORDER BY id DESC LIMIT 50
                """,
                (since_ts,),
            ).fetchall()
            for er in err_rows:
                items.append({
                    "id": f"agent-error-{er['id']}",
                    "type": "agent_error",
                    "ts": er["ts"],
                    "title": f"Errore: {er['text'][:80]}",
                    "detail": er["text"],
                    "ticker": None,
                    "ref": None,
                    "severity": "critical",
                })

            # 10. Risk limits
            lim_rows = conn.execute(
                """
                SELECT version, ts, actor, reason FROM risk_limits_versions
                WHERE ts >= ?
                ORDER BY version DESC LIMIT 50
                """,
                (since_ts,),
            ).fetchall()
            for lr in lim_rows:
                items.append({
                    "id": f"risk-limits-{lr['version']}",
                    "type": "risk_limits",
                    "ts": lr["ts"],
                    "title": f"Limiti di rischio v{lr['version']} modificati da {lr['actor']}",
                    "detail": lr["reason"],
                    "ticker": None,
                    "ref": {"type": "risk_limits", "id": lr["version"]},
                    "severity": "attention",
                })

            # Counts
            counts = {
                "trades": len(trade_rows),
                "orders_pending": len(ord_rows),
                "proposals_pending": len(prop_pending),
                "proposals_decided": len(prop_decided),
                "alerts": len(alert_rows),
                "agent_errors": len(err_rows),
            }

            # Sort all items by ts DESC and cap at 50
            items.sort(key=lambda x: str(x.get("ts", "")), reverse=True)
            capped_items = items[:50]

            # Summary text from cache or Bridge
            summary_text = None
            summary_ts = None
            cached_sum_row = conn.execute(
                "SELECT value, updated_ts FROM briefing_state WHERE key = ?",
                (f"summary:{since_ts}",),
            ).fetchone()
            if cached_sum_row:
                summary_text = str(cached_sum_row["value"])
                summary_ts = str(cached_sum_row["updated_ts"])
            elif getattr(self._runtime, "bridge_runner", None):
                res = self._runtime.bridge_runner.generate_briefing_summary(
                    since=since_ts, items=capped_items, portfolio=portfolio_data
                )
                if res:
                    summary_text, summary_ts = res

            return {
                "since": since_ts,
                "generated_ts": now_iso,
                "summary_text": summary_text,
                "summary_ts": summary_ts,
                "portfolio": portfolio_data,
                "counts": counts,
                "items": capped_items,
            }
        finally:
            if self.db_path != ":memory:":
                conn.close()

