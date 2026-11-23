"""OfficeDB: SQLite repository for the Agent Office.

Implements SQLite persistence with WAL mode, foreign keys enabled, versioned
migrations, and thin repository methods for agent chats, scheduled tasks,
cycles, ticker state, orders, trades, LLM/tool logs, blobs, and financial cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format with Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# --- Migration definitions ---

_MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "001_core_tables",
        """
        -- Agents & Chats
        CREATE TABLE IF NOT EXISTS agents (
            name TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            prompt_hash TEXT
        );

        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            topic TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (agent) REFERENCES agents(name) ON DELETE CASCADE,
            UNIQUE(agent, topic)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            author TEXT NOT NULL,
            ts TEXT NOT NULL,
            text TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('original', 'summary')),
            cycle_id INTEGER,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_messages_chat_ts ON messages(chat_id, ts);

        -- Work: Scheduled tasks, cycles, ticker_state, watchlist
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            chat TEXT NOT NULL,
            when_ts TEXT NOT NULL,
            source TEXT NOT NULL,
            reason TEXT NOT NULL,
            data_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL
                CHECK (status IN ('pending', 'delivered', 'merged', 'failed', 'cancelled')),
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_ts TEXT,
            merged_into INTEGER,
            FOREIGN KEY (merged_into) REFERENCES scheduled_tasks(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_due ON scheduled_tasks(status, when_ts);

        CREATE TABLE IF NOT EXISTS cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            status TEXT NOT NULL,
            opened_ts TEXT NOT NULL,
            closed_ts TEXT,
            outcome TEXT,
            budget_used_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_cycles_ticker ON cycles(ticker, status);

        CREATE TABLE IF NOT EXISTS ticker_state (
            ticker TEXT PRIMARY KEY,
            state_json TEXT NOT NULL DEFAULT '{}',
            updated_ts TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT PRIMARY KEY,
            added_ts TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT ''
        );

        -- Orders, Trades, Portfolio
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            draft_json TEXT NOT NULL,
            draft_hash TEXT NOT NULL,
            approval_status TEXT NOT NULL
                CHECK (
                    approval_status IN ('auto', 'pending', 'approved', 'rejected', 'expired')
                ),
            client_order_id TEXT NOT NULL UNIQUE,
            broker_order_id TEXT,
            status TEXT NOT NULL,
            created_ts TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders(client_order_id);

        CREATE TABLE IF NOT EXISTS order_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            event TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            entry_order_id INTEGER NOT NULL,
            opened_ts TEXT NOT NULL,
            closed_ts TEXT,
            exit_reason TEXT
                CHECK (exit_reason IS NULL OR exit_reason IN ('tp', 'sl', 'pm_sell', 'expired', 'reconciled_unknown')),
            entry_price REAL NOT NULL,
            exit_price REAL,
            qty REAL NOT NULL,
            events_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (entry_order_id) REFERENCES orders(id)
        );

        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            ts TEXT PRIMARY KEY,
            equity REAL NOT NULL,
            cash REAL NOT NULL,
            positions_json TEXT NOT NULL DEFAULT '[]'
        );

        -- Registry & Blobs
        CREATE TABLE IF NOT EXISTS blobs (
            hash TEXT PRIMARY KEY,
            compressed BLOB NOT NULL
        );

        CREATE TABLE IF NOT EXISTS llm_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            agent TEXT NOT NULL,
            chat_id INTEGER,
            model TEXT NOT NULL,
            prompt_hash TEXT,
            tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0,
            cost REAL NOT NULL DEFAULT 0.0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            prompt_blob TEXT,
            response_blob TEXT,
            FOREIGN KEY (prompt_blob) REFERENCES blobs(hash),
            FOREIGN KEY (response_blob) REFERENCES blobs(hash)
        );
        CREATE INDEX IF NOT EXISTS idx_llm_calls_agent_ts ON llm_calls(agent, ts);

        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            agent TEXT NOT NULL,
            chat_id INTEGER,
            tool TEXT NOT NULL,
            params_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '{}',
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tool_calls_agent_ts ON tool_calls(agent, ts);

        CREATE TABLE IF NOT EXISTS cli_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            command TEXT NOT NULL,
            args_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS inbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,
            text TEXT NOT NULL,
            read INTEGER NOT NULL DEFAULT 0
        );

        -- Financial Data
        CREATE TABLE IF NOT EXISTS securities (
            symbol TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            sector TEXT,
            industry TEXT
        );

        CREATE TABLE IF NOT EXISTS prices_ohlcv (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            ts TEXT NOT NULL,
            interval TEXT NOT NULL,
            o REAL NOT NULL,
            h REAL NOT NULL,
            l REAL NOT NULL,
            c REAL NOT NULL,
            v REAL NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            UNIQUE(symbol, ts, interval)
        );
        CREATE INDEX IF NOT EXISTS idx_prices_lookup ON prices_ohlcv(symbol, interval, ts);

        CREATE TABLE IF NOT EXISTS fundamentals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            data_json TEXT NOT NULL,
            UNIQUE(symbol, source, fetched_at)
        );

        CREATE TABLE IF NOT EXISTS ratios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            data_json TEXT NOT NULL,
            UNIQUE(symbol, source, fetched_at)
        );

        CREATE TABLE IF NOT EXISTS earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            data_json TEXT NOT NULL,
            UNIQUE(symbol, date, source)
        );

        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            data_json TEXT NOT NULL,
            UNIQUE(symbol, source, fetched_at)
        );

        CREATE TABLE IF NOT EXISTS insider (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            data_json TEXT NOT NULL,
            UNIQUE(symbol, transaction_date, source, fetched_at)
        );

        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            headline TEXT NOT NULL,
            summary TEXT,
            full_text TEXT,
            published_at TEXT NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            UNIQUE(symbol, published_at, headline)
        );

        CREATE TABLE IF NOT EXISTS macro_series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            value REAL NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            UNIQUE(series_id, ts)
        );

        CREATE TABLE IF NOT EXISTS econ_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            event_name TEXT NOT NULL,
            event_ts TEXT NOT NULL,
            impact TEXT,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            data_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(event_id, source)
        );

        CREATE TABLE IF NOT EXISTS sector_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sector TEXT NOT NULL,
            ts TEXT NOT NULL,
            perf_json TEXT NOT NULL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            UNIQUE(sector, ts, source)
        );
        """,
    ),
    (
        2,
        "002_events_table",
        """
        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT NOT NULL,
            type       TEXT NOT NULL,
            actor      TEXT NOT NULL,
            subject    TEXT,
            command_id TEXT,
            payload    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_type_ts ON events(type, ts);
        CREATE UNIQUE INDEX IF NOT EXISTS events_command_once ON events(command_id)
            WHERE command_id IS NOT NULL AND type = 'command.accepted';
        """,
    ),
    (
        3,
        "003_reconciled_unknown_exit_reason",
        """
        PRAGMA foreign_keys = OFF;
        CREATE TABLE IF NOT EXISTS trades_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            entry_order_id INTEGER NOT NULL,
            opened_ts TEXT NOT NULL,
            closed_ts TEXT,
            exit_reason TEXT
                CHECK (exit_reason IS NULL OR exit_reason IN ('tp', 'sl', 'pm_sell', 'expired', 'reconciled_unknown')),
            entry_price REAL NOT NULL,
            exit_price REAL,
            qty REAL NOT NULL,
            events_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (entry_order_id) REFERENCES orders(id)
        );
        INSERT INTO trades_new SELECT id, ticker, entry_order_id, opened_ts, closed_ts, exit_reason, entry_price, exit_price, qty, events_json FROM trades;
        DROP TABLE trades;
        ALTER TABLE trades_new RENAME TO trades;
        PRAGMA foreign_keys = ON;
        """,
    ),
    (
        4,
        "004_watchlist_author",
        "ALTER TABLE watchlist ADD COLUMN added_by TEXT NOT NULL DEFAULT 'unknown';",
    ),
    (
        5,
        "005_chart_annotations",
        """
        CREATE TABLE chart_annotations (
            id TEXT PRIMARY KEY, ticker TEXT NOT NULL, timeframe TEXT,
            drawing_json TEXT NOT NULL, author TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'struck')),
            struck_by TEXT, struck_at TEXT
        );
        CREATE INDEX chart_annotations_ticker ON chart_annotations(ticker, status);
    """,
    ),
    (
        6,
        "006_cockpit_office_backend",
        """
        ALTER TABLE agents ADD COLUMN status TEXT NOT NULL DEFAULT 'idle';
        ALTER TABLE agents ADD COLUMN current_task_json TEXT;
        ALTER TABLE agents ADD COLUMN last_activity_ts TEXT;

        ALTER TABLE tool_calls ADD COLUMN duration_ms INTEGER;
        ALTER TABLE tool_calls ADD COLUMN cycle_id INTEGER;
        ALTER TABLE tool_calls ADD COLUMN compacted INTEGER NOT NULL DEFAULT 0;
        CREATE INDEX IF NOT EXISTS idx_tool_calls_cycle ON tool_calls(cycle_id);
        """,
    ),
    (
        7,
        "007_portfolio_backend",
        """
        CREATE TABLE IF NOT EXISTS risk_limits_versions (
            version INTEGER PRIMARY KEY,
            ts TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL
        );
        ALTER TABLE trades ADD COLUMN stop_price REAL;
        ALTER TABLE trades ADD COLUMN target_price REAL;
        ALTER TABLE trades ADD COLUMN initial_stop REAL;
        ALTER TABLE trades ADD COLUMN proposed_by TEXT;
        ALTER TABLE trades ADD COLUMN closed_qty REAL NOT NULL DEFAULT 0;
        ALTER TABLE trades ADD COLUMN realized_pnl REAL;
        """,
    ),
    (
        8,
        "008_ticker_dossier_versions",
        """
        CREATE TABLE dossier_versions (
            ticker TEXT NOT NULL, version INTEGER NOT NULL, ts TEXT NOT NULL,
            author TEXT NOT NULL, sections_json TEXT NOT NULL, document_json TEXT NOT NULL,
            PRIMARY KEY (ticker, version)
        );
        CREATE TABLE proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL, agent TEXT NOT NULL,
            status TEXT NOT NULL, direction TEXT NOT NULL, conviction REAL NOT NULL,
            sizing_fraction REAL, risk_reward REAL, submitted_ts TEXT NOT NULL,
            decided_ts TEXT, decided_by TEXT, reason TEXT NOT NULL, cycle_id INTEGER
        );
        """,
    ),
    (
        9,
        "009_bridge_and_briefing",
        """
        CREATE TABLE IF NOT EXISTS bridge_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_ts TEXT NOT NULL,
            updated_ts TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'idle' CHECK(status IN ('idle', 'thinking')),
            archived INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_bridge_conversations_updated ON bridge_conversations(updated_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_bridge_conversations_archived ON bridge_conversations(archived);

        CREATE TABLE IF NOT EXISTS bridge_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES bridge_conversations(id) ON DELETE CASCADE,
            command TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            summary TEXT NOT NULL,
            capital INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'confirmed', 'dismissed', 'executed', 'failed')),
            preview_json TEXT,
            result_reasons_json TEXT NOT NULL DEFAULT '[]',
            decided_ts TEXT,
            decided_by TEXT,
            created_ts TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_bridge_actions_conv ON bridge_actions(conversation_id, status);
        CREATE INDEX IF NOT EXISTS idx_bridge_actions_status ON bridge_actions(status);

        CREATE TABLE IF NOT EXISTS bridge_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES bridge_conversations(id) ON DELETE CASCADE,
            author TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('text', 'agent_relay', 'action', 'error')),
            text TEXT NOT NULL,
            ts TEXT NOT NULL,
            context_json TEXT,
            refs_json TEXT,
            action_id INTEGER REFERENCES bridge_actions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_bridge_messages_conv ON bridge_messages(conversation_id, id ASC);

        CREATE TABLE IF NOT EXISTS bridge_relay_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL,
            topic TEXT NOT NULL,
            conversation_id INTEGER NOT NULL REFERENCES bridge_conversations(id) ON DELETE CASCADE,
            created_ts TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_bridge_relay ON bridge_relay_subscriptions(agent, topic);

        CREATE TABLE IF NOT EXISTS briefing_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_ts TEXT NOT NULL
        );
        """,
    ),
]


class OfficeDB:
    """Repository gateway for all agent-office persistence."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._on_commit_callbacks: list[Callable[[], None]] | None = None
        self._tx_depth = 0
        self.event_log: Any = None
        self.on_bridge_relay: Callable[[int], None] | None = None
        self._connection = sqlite3.connect(
            str(self.path), isolation_level=None, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._init_migrations()
        self._migrate()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def _init_migrations(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )

    def _migrate(self) -> None:
        rows = self._connection.execute(
            "SELECT version FROM schema_version ORDER BY version"
        ).fetchall()
        applied = {row["version"] for row in rows}

        for version, name, sql in _MIGRATIONS:
            if version not in applied:
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    self._connection.executescript(sql)
                    self._connection.execute(
                        "INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?)",
                        (version, name, utc_now_iso()),
                    )
                    self._connection.commit()
                except Exception:
                    self._connection.rollback()
                    raise

    @property
    def schema_version(self) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version"
        ).fetchone()
        return int(row[0]) if row else 0

    @contextmanager
    def transaction(self) -> Iterator[Self]:
        with self._lock:
            is_outer = self._tx_depth == 0
            if is_outer:
                self._connection.execute("BEGIN IMMEDIATE")
                self._on_commit_callbacks = []
            self._tx_depth += 1
            try:
                yield self
            except Exception:
                if is_outer:
                    self._on_commit_callbacks = None
                    self._connection.rollback()
                raise
            else:
                if is_outer:
                    self._connection.commit()
                    callbacks = self._on_commit_callbacks or []
                    self._on_commit_callbacks = None
                    for cb in callbacks:
                        try:
                            cb()
                        except Exception:
                            logger.exception("Error executing on_commit callback")
            finally:
                self._tx_depth -= 1

    def add_on_commit(self, callback: Callable[[], None]) -> None:
        """Register a callback to run after the current transaction commits, or run now if autocommit."""
        with self._lock:
            if self._on_commit_callbacks is not None:
                self._on_commit_callbacks.append(callback)
            else:
                callback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def db_size_bytes(self) -> int:
        if self.path == Path(":memory:"):
            page_count = self._connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = self._connection.execute("PRAGMA page_size").fetchone()[0]
            return int(page_count * page_size)
        try:
            total = self.path.stat().st_size
            wal = self.path.with_name(self.path.name + "-wal")
            if wal.is_file():
                total += wal.stat().st_size
            shm = self.path.with_name(self.path.name + "-shm")
            if shm.is_file():
                total += shm.stat().st_size
            return total
        except OSError:
            return 0

    def check_db_size_alert(self, threshold_mb: int, ts: str | None = None) -> bool:
        """Check if DB size exceeds threshold_mb.

        If so, creates an unread inbox alert if one doesn't already exist (US 102, 117).
        """
        if threshold_mb <= 0:
            return False
        size_bytes = self.db_size_bytes()
        threshold_bytes = threshold_mb * 1024 * 1024
        if size_bytes > threshold_bytes:
            row = self._connection.execute(
                "SELECT id FROM inbox WHERE kind = 'db_size' AND read = 0 LIMIT 1"
            ).fetchone()
            if not row:
                size_mb = size_bytes / (1024 * 1024)
                self.add_inbox(
                    kind="db_size",
                    text=(
                        f"Allarme dimensione DB: {size_mb:.2f} MB supera la soglia configurata "
                        f"di {threshold_mb} MB"
                    ),
                    ts=ts,
                )
            return True
        return False

    # --- Agent registration ---

    def register_agent(
        self, name: str, role: str, config: dict | str = "{}", prompt_hash: str | None = None
    ) -> None:
        config_json = config if isinstance(config, str) else json.dumps(config)
        self._connection.execute(
            """
            INSERT INTO agents (name, role, config_json, prompt_hash)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                role = excluded.role,
                config_json = excluded.config_json,
                prompt_hash = excluded.prompt_hash
            """,
            (name, role, config_json, prompt_hash),
        )

    def set_agent_status(
        self, agent: str, status: str, current_task: dict | None = None,
        ts: str | None = None,
    ) -> None:
        if status not in ("working", "waiting", "idle"):
            raise ValueError("Invalid agent status")
        ts = ts or utc_now_iso()
        with self.transaction():
            self._connection.execute(
                "INSERT INTO agents(name, role, status, current_task_json, last_activity_ts) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET "
                "status=excluded.status, current_task_json=excluded.current_task_json, "
                "last_activity_ts=excluded.last_activity_ts",
                (agent, agent, status, json.dumps(current_task) if current_task else None, ts),
            )
            if self.event_log:
                self.event_log.append(
                    "agent.status", f"agent:{agent}",
                    {"agent": agent, "status": status, "current_task": current_task, "ts": ts},
                    actor=agent,
                )

    def get_agent(self, name: str) -> dict | None:
        row = self._connection.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    # --- Chats & Messages ---

    def create_chat(self, agent: str, topic: str) -> int:
        with self._lock:
            self._connection.execute(
                "INSERT INTO agents(name, role) VALUES (?, ?) ON CONFLICT(name) DO NOTHING",
                (agent, agent),
            )
            self._connection.execute(
                "INSERT INTO chats (agent, topic, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(agent, topic) DO NOTHING", (agent, topic, utc_now_iso()),
            )
            row = self._connection.execute(
                "SELECT id FROM chats WHERE agent = ? AND topic = ?", (agent, topic)
            ).fetchone()
            return int(row["id"])

    def get_chat(self, chat_id: int) -> dict | None:
        row = self._connection.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        return dict(row) if row else None

    def get_or_create_chat(self, agent: str, topic: str) -> int:
        return self.create_chat(agent, topic)

    def list_chats(self, agent: str | None = None) -> list[dict]:
        if agent is not None:
            rows = self._connection.execute(
                "SELECT * FROM chats WHERE agent = ? ORDER BY id", (agent,)
            ).fetchall()
        else:
            rows = self._connection.execute("SELECT * FROM chats ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def append_message(
        self,
        chat_id: int,
        author: str,
        text: str,
        kind: str = "original",
        cycle_id: int | None = None,
        ts: str | None = None,
    ) -> int:
        if kind not in ("original", "summary"):
            raise ValueError(f"Invalid message kind: {kind}")
        ts = ts or utc_now_iso()
        with self.transaction():
            cursor = self._connection.execute(
                """
                INSERT INTO messages (chat_id, author, ts, text, kind, cycle_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chat_id, author, ts, text, kind, cycle_id),
            )
            message_id = int(cursor.lastrowid)
            chat = self.get_chat(chat_id)
            if self.event_log:
                self.event_log.append(
                    "chat.message", f"chat:{chat_id}",
                    {"chat_id": chat_id, "message_id": message_id,
                     "agent": chat["agent"] if chat else None,
                     "topic": chat["topic"] if chat else None, "author": author,
                     "text": text, "kind": kind, "cycle_id": cycle_id, "ts": ts},
                    actor=author,
                )

            # Check for bridge relay subscriptions
            if chat and author not in ("bridge", "system", "user", "luca"):
                agent_name = str(chat["agent"])
                topic_name = str(chat["topic"])
                conv_ids = self.list_bridge_relay_subscriptions(agent_name, topic_name)
                if conv_ids:
                    ctx = {"page": "ufficio", "ticker": topic_name, "ref": {"type": "agent", "id": author}}
                    for conv_id in conv_ids:
                        b_msg_id = self.append_bridge_message(
                            conversation_id=conv_id,
                            author=author,
                            kind="agent_relay",
                            text=text,
                            ts=ts,
                            context=ctx,
                        )
                        if self.event_log:
                            b_msg = self.get_bridge_message(b_msg_id)
                            if b_msg:
                                payload_msg = {
                                    "id": b_msg["id"],
                                    "conversation_id": conv_id,
                                    "author": author,
                                    "kind": "agent_relay",
                                    "text": text,
                                    "ts": ts,
                                    "context": ctx,
                                    "refs": [],
                                    "action": None,
                                }
                                self.event_log.append(
                                    "bridge.message",
                                    f"bridge_conv:{conv_id}",
                                    {"conversation_id": conv_id, "message": payload_msg},
                                    actor=author,
                                )
                        if self.on_bridge_relay:
                            self.add_on_commit(lambda cid=conv_id, callback=self.on_bridge_relay: callback(cid))
                    self._connection.execute(
                        "DELETE FROM bridge_relay_subscriptions WHERE agent = ? AND topic = ?",
                        (agent_name, topic_name),
                    )
            return message_id

    def list_messages(
        self,
        chat_id: int,
        kind: str | None = None,
        limit: int | None = None,
        since_ts: str | None = None,
    ) -> list[dict]:
        query = "SELECT * FROM messages WHERE chat_id = ?"
        params: list[Any] = [chat_id]
        if kind:
            query += " AND kind = ?"
            params.append(kind)
        if since_ts:
            query += " AND ts >= ?"
            params.append(since_ts)
        query += " ORDER BY ts ASC, id ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = self._connection.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def compact_chat(
        self,
        chat_id: int,
        summary_text: str,
        author: str = "system",
        cycle_id: int | None = None,
        ts: str | None = None,
    ) -> int:
        """Compact chat by inserting a summary message row without deleting original messages."""
        return self.append_message(
            chat_id=chat_id,
            author=author,
            text=summary_text,
            kind="summary",
            cycle_id=cycle_id,
            ts=ts,
        )

    # --- Scheduled Tasks ---

    def enqueue_scheduled_task(
        self,
        agent: str,
        chat: str,
        when_ts: str,
        source: str,
        reason: str,
        data: dict | str = "{}",
        status: str = "pending",
    ) -> int:
        data_json = data if isinstance(data, str) else json.dumps(data)
        cursor = self._connection.execute(
            """
            INSERT INTO scheduled_tasks (
                agent, chat, when_ts, source, reason, data_json, status, attempts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (agent, chat, when_ts, source, reason, data_json, status),
        )
        return int(cursor.lastrowid)

    def next_due_ts(self) -> str | None:
        """Return earliest due timestamp of any pending scheduled task."""
        row = self._connection.execute(
            """
            SELECT MIN(COALESCE(next_attempt_ts, when_ts))
            FROM scheduled_tasks
            WHERE status = 'pending'
            """
        ).fetchone()
        return row[0] if row and row[0] is not None else None

    def due_scheduled_tasks(self, now_ts: str | None = None, limit: int = 50) -> list[dict]:
        ts = now_ts or utc_now_iso()
        rows = self._connection.execute(
            """
            SELECT * FROM scheduled_tasks
            WHERE status = 'pending' AND when_ts <= ?
              AND (next_attempt_ts IS NULL OR next_attempt_ts <= ?)
            ORDER BY when_ts ASC, id ASC
            LIMIT ?
            """,
            (ts, ts, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_scheduled_task(
        self,
        task_id: int,
        status: str,
        next_attempt_ts: str | None = None,
        merged_into: int | None = None,
    ) -> None:
        if status not in ("pending", "delivered", "merged", "failed", "cancelled"):
            raise ValueError(f"Invalid scheduled task status: {status}")
        self._connection.execute(
            """
            UPDATE scheduled_tasks
            SET status = ?,
                attempts = attempts + (CASE WHEN ? IN ('delivered', 'failed') THEN 1 ELSE 0 END),
                next_attempt_ts = ?,
                merged_into = ?
            WHERE id = ?
            """,
            (status, status, next_attempt_ts, merged_into, task_id),
        )

    def get_scheduled_task(self, task_id: int) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row else None

    # --- Cycles ---

    def open_cycle(
        self,
        ticker: str,
        status: str = "open",
        opened_ts: str | None = None,
        budget_used: dict | str = "{}",
    ) -> int:
        opened_ts = opened_ts or utc_now_iso()
        budget_json = budget_used if isinstance(budget_used, str) else json.dumps(budget_used)
        with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO cycles (ticker, status, opened_ts, budget_used_json) VALUES (?, ?, ?, ?)",
                (ticker, status, opened_ts, budget_json),
            )
            return int(cursor.lastrowid)

    def close_cycle(
        self,
        cycle_id: int,
        outcome: str,
        closed_ts: str | None = None,
        budget_used: dict | str | None = None,
    ) -> None:
        with self._lock:
            closed_ts = closed_ts or utc_now_iso()
            if budget_used is not None:
                budget_json = budget_used if isinstance(budget_used, str) else json.dumps(budget_used)
                self._connection.execute(
                    """
                    UPDATE cycles
                    SET status = 'closed', outcome = ?, closed_ts = ?, budget_used_json = ?
                    WHERE id = ?
                    """,
                    (outcome, closed_ts, budget_json, cycle_id),
                )
            else:
                self._connection.execute(
                    """
                    UPDATE cycles
                    SET status = 'closed', outcome = ?, closed_ts = ?
                    WHERE id = ?
                    """,
                    (outcome, closed_ts, cycle_id),
                )

    def get_cycle(self, cycle_id: int) -> dict | None:
        row = self._connection.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
        return dict(row) if row else None

    def get_active_cycle(self, ticker: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM cycles WHERE ticker = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return dict(row) if row else None

    # --- Ticker State ---

    def set_ticker_state(
        self, ticker: str, state: dict | str, updated_ts: str | None = None
    ) -> None:
        updated_ts = updated_ts or utc_now_iso()
        state_json = state if isinstance(state, str) else json.dumps(state)
        self._connection.execute(
            """
            INSERT INTO ticker_state (ticker, state_json, updated_ts)
            VALUES (?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                state_json = excluded.state_json,
                updated_ts = excluded.updated_ts
            """,
            (ticker, state_json, updated_ts),
        )

    def get_ticker_state(self, ticker: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM ticker_state WHERE ticker = ?", (ticker,)
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def write_dossier_section(
        self, ticker: str, section: str, value: Any, author: str, ts: str
    ) -> int:
        ticker = ticker.upper().strip()
        with self.transaction():
            row = self._connection.execute(
                "SELECT version, document_json FROM dossier_versions "
                "WHERE ticker = ? ORDER BY version DESC LIMIT 1", (ticker,)
            ).fetchone()
            document = json.loads(row["document_json"]) if row else {"ticker": ticker, "desks": []}
            if isinstance(value, dict):
                value = {"author": author, "ts": ts, "reference_date": ts[:10], "confidence": None,
                         "status": "active", **value}
            if section in ("notes", "lessons", "decisions"):
                document.setdefault(section, []).append(value)
            elif section == "desks":
                document["desks"] = [item for item in document["desks"] if item["agent"] != author]
                document["desks"].append(value)
            else:
                document[section] = value
            version = row["version"] + 1 if row else 1
            document.update(version=version, updated_ts=ts, updated_by=author)
            self._connection.execute(
                "INSERT INTO dossier_versions VALUES (?, ?, ?, ?, ?, ?)",
                (ticker, version, ts, author, json.dumps([section]), json.dumps(document)),
            )
            if self.event_log is not None:
                self.event_log.append("dossier.updated", ticker, {
                    "ticker": ticker, "version": version, "sections": [section],
                }, author)
            return version

    # --- Watchlist ---

    def add_watchlist(
        self, ticker: str, note: str = "", added_ts: str | None = None, added_by: str = "unknown"
    ) -> None:
        added_ts = added_ts or utc_now_iso()
        self._connection.execute(
            """
            INSERT INTO watchlist (ticker, added_ts, note, added_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET note = excluded.note
            """,
            (ticker, added_ts, note, added_by),
        )

    def remove_watchlist(self, ticker: str) -> bool:
        cursor = self._connection.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))
        return cursor.rowcount > 0

    def list_watchlist(self) -> list[dict]:
        rows = self._connection.execute("SELECT * FROM watchlist ORDER BY ticker").fetchall()
        return [dict(r) for r in rows]

    # --- Blobs ---

    def put_blob(self, data: str | bytes) -> str:
        """Store zlib-compressed data deduplicated by sha256 hash. Returns hash."""
        raw_bytes = data.encode("utf-8") if isinstance(data, str) else data
        digest = hashlib.sha256(raw_bytes).hexdigest()
        compressed = zlib.compress(raw_bytes)
        self._connection.execute(
            """
            INSERT OR IGNORE INTO blobs (hash, compressed)
            VALUES (?, ?)
            """,
            (digest, compressed),
        )
        return digest

    def get_blob(self, blob_hash: str) -> bytes | None:
        row = self._connection.execute(
            "SELECT compressed FROM blobs WHERE hash = ?", (blob_hash,)
        ).fetchone()
        if not row:
            return None
        return zlib.decompress(row["compressed"])

    def get_blob_text(self, blob_hash: str) -> str | None:
        raw = self.get_blob(blob_hash)
        if raw is None:
            return None
        return raw.decode("utf-8")

    # --- Orders, Events, Trades ---

    def insert_order(
        self,
        ticker: str,
        side: str,
        draft: dict | str,
        draft_hash: str,
        approval_status: str,
        client_order_id: str,
        status: str,
        broker_order_id: str | None = None,
        created_ts: str | None = None,
    ) -> int:
        if approval_status not in ("auto", "pending", "approved", "rejected", "expired"):
            raise ValueError(f"Invalid approval status: {approval_status}")
        created_ts = created_ts or utc_now_iso()
        draft_json = draft if isinstance(draft, str) else json.dumps(draft)
        cursor = self._connection.execute(
            """
            INSERT INTO orders (
                ticker, side, draft_json, draft_hash, approval_status,
                client_order_id, broker_order_id, status, created_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                side,
                draft_json,
                draft_hash,
                approval_status,
                client_order_id,
                broker_order_id,
                status,
                created_ts,
            ),
        )
        return int(cursor.lastrowid)

    def get_order(self, order_id: int) -> dict | None:
        row = self._connection.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return dict(row) if row else None

    def get_order_by_client_id(self, client_order_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_order_status(
        self,
        order_id: int,
        status: str,
        broker_order_id: str | None = None,
        approval_status: str | None = None,
    ) -> None:
        updates = ["status = ?"]
        params: list[Any] = [status]
        if broker_order_id is not None:
            updates.append("broker_order_id = ?")
            params.append(broker_order_id)
        if approval_status is not None:
            if approval_status not in ("auto", "pending", "approved", "rejected", "expired"):
                raise ValueError(f"Invalid approval status: {approval_status}")
            updates.append("approval_status = ?")
            params.append(approval_status)
        params.append(order_id)
        self._connection.execute(
            f"UPDATE orders SET {', '.join(updates)} WHERE id = ?",
            params,
        )

    def insert_order_event(
        self, order_id: int, event: str, detail: dict | str = "{}", ts: str | None = None
    ) -> int:
        ts = ts or utc_now_iso()
        detail_json = detail if isinstance(detail, str) else json.dumps(detail)
        cursor = self._connection.execute(
            """
            INSERT INTO order_events (order_id, ts, event, detail_json)
            VALUES (?, ?, ?, ?)
            """,
            (order_id, ts, event, detail_json),
        )
        return int(cursor.lastrowid)

    def list_order_events(self, order_id: int) -> list[dict]:
        rows = self._connection.execute(
            "SELECT * FROM order_events WHERE order_id = ? ORDER BY ts ASC, id ASC",
            (order_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def insert_trade(
        self,
        ticker: str,
        entry_order_id: int,
        entry_price: float,
        qty: float,
        opened_ts: str | None = None,
        closed_ts: str | None = None,
        exit_reason: str | None = None,
        exit_price: float | None = None,
        events: list | str = "[]",
        stop_price: float | None = None,
        target_price: float | None = None,
        initial_stop: float | None = None,
        proposed_by: str | None = None,
    ) -> int:
        if exit_reason is not None and exit_reason not in ("tp", "sl", "pm_sell", "expired"):
            raise ValueError(f"Invalid exit reason: {exit_reason}")
        opened_ts = opened_ts or utc_now_iso()
        events_json = events if isinstance(events, str) else json.dumps(events)
        cursor = self._connection.execute(
            """
            INSERT INTO trades (
                ticker, entry_order_id, opened_ts, closed_ts, exit_reason,
                entry_price, exit_price, qty, events_json,
                stop_price, target_price, initial_stop, proposed_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                entry_order_id,
                opened_ts,
                closed_ts,
                exit_reason,
                entry_price,
                exit_price,
                qty,
                events_json,
                stop_price,
                target_price,
                initial_stop if initial_stop is not None else stop_price,
                proposed_by,
            ),
        )
        return int(cursor.lastrowid)

    def update_trade_levels(
        self,
        trade_id: int,
        stop_price: float | None = None,
        target_price: float | None = None,
        events: list | str | None = None,
    ) -> None:
        """Aggiorna stop/target correnti (None = invariato) ed eventualmente gli eventi."""
        sets: list[str] = []
        params: list[Any] = []
        if stop_price is not None:
            sets.append("stop_price = ?")
            params.append(stop_price)
        if target_price is not None:
            sets.append("target_price = ?")
            params.append(target_price)
        if events is not None:
            sets.append("events_json = ?")
            params.append(events if isinstance(events, str) else json.dumps(events))
        if not sets:
            return
        params.append(trade_id)
        self._connection.execute(f"UPDATE trades SET {', '.join(sets)} WHERE id = ?", params)

    def add_trade_partial_close(
        self, trade_id: int, qty: float, pnl: float, events: list | str | None = None
    ) -> None:
        """Registra una chiusura parziale: quantità chiusa e PnL realizzato cumulati."""
        events_json = None if events is None else (
            events if isinstance(events, str) else json.dumps(events)
        )
        self._connection.execute(
            """
            UPDATE trades
            SET closed_qty = closed_qty + ?,
                realized_pnl = COALESCE(realized_pnl, 0) + ?,
                events_json = COALESCE(?, events_json)
            WHERE id = ?
            """,
            (qty, pnl, events_json, trade_id),
        )

    def get_trade(self, trade_id: int) -> dict | None:
        row = self._connection.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return dict(row) if row else None

    def close_trade(
        self,
        trade_id: int,
        exit_price: float | None = None,
        exit_reason: str = "tp",
        closed_ts: str | None = None,
        events: list | str | None = None,
        realized_pnl: float | None = None,
        closed_qty: float | None = None,
    ) -> None:
        if exit_reason not in ("tp", "sl", "pm_sell", "expired", "reconciled_unknown"):
            raise ValueError(f"Invalid exit reason: {exit_reason}")
        closed_ts = closed_ts or utc_now_iso()
        if realized_pnl is not None or closed_qty is not None:
            self._connection.execute(
                """
                UPDATE trades
                SET realized_pnl = COALESCE(?, realized_pnl), closed_qty = COALESCE(?, closed_qty)
                WHERE id = ?
                """,
                (realized_pnl, closed_qty, trade_id),
            )
        if events is not None:
            events_json = events if isinstance(events, str) else json.dumps(events)
            self._connection.execute(
                """
                UPDATE trades
                SET exit_price = ?, exit_reason = ?, closed_ts = ?, events_json = ?
                WHERE id = ?
                """,
                (exit_price, exit_reason, closed_ts, events_json, trade_id),
            )
        else:
            self._connection.execute(
                """
                UPDATE trades
                SET exit_price = ?, exit_reason = ?, closed_ts = ?
                WHERE id = ?
                """,
                (exit_price, exit_reason, closed_ts, trade_id),
            )

    # --- Risk limits (versioned) ---

    def latest_risk_limits_version(self) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM risk_limits_versions ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def insert_risk_limits_version(
        self, actor: str, reason: str, before: dict, after: dict, ts: str | None = None
    ) -> int:
        ts = ts or utc_now_iso()
        row = self._connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM risk_limits_versions"
        ).fetchone()
        version = int(row[0])
        self._connection.execute(
            """
            INSERT INTO risk_limits_versions (version, ts, actor, reason, before_json, after_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (version, ts, actor, reason, json.dumps(before), json.dumps(after)),
        )
        return version

    def list_risk_limits_versions(self, limit: int = 50) -> list[dict]:
        rows = self._connection.execute(
            "SELECT * FROM risk_limits_versions ORDER BY version DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Portfolio Snapshots ---

    def insert_portfolio_snapshot(
        self, equity: float, cash: float, positions: list | str = "[]", ts: str | None = None
    ) -> None:
        ts = ts or utc_now_iso()
        pos_json = positions if isinstance(positions, str) else json.dumps(positions)
        self._connection.execute(
            """
            INSERT OR REPLACE INTO portfolio_snapshots (ts, equity, cash, positions_json)
            VALUES (?, ?, ?, ?)
            """,
            (ts, equity, cash, pos_json),
        )

    def latest_portfolio_snapshot(self) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    # --- Inbox ---

    def add_inbox(self, kind: str, text: str, ts: str | None = None) -> int:
        ts = ts or utc_now_iso()
        cursor = self._connection.execute(
            "INSERT INTO inbox (ts, kind, text, read) VALUES (?, ?, ?, 0)",
            (ts, kind, text),
        )
        return int(cursor.lastrowid)

    def list_inbox(self, unread_only: bool = False, limit: int = 50) -> list[dict]:
        query = "SELECT * FROM inbox"
        params: list[Any] = []
        if unread_only:
            query += " WHERE read = 0"
        query += " ORDER BY ts DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = self._connection.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def mark_inbox_read(self, item_id: int) -> None:
        self._connection.execute("UPDATE inbox SET read = 1 WHERE id = ?", (item_id,))

    # --- Registry logging ---

    def log_llm_call(
        self,
        agent: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost: float,
        duration_ms: int,
        chat_id: int | None = None,
        prompt_hash: str | None = None,
        prompt_text: str | None = None,
        response_text: str | None = None,
        prompt_blob: str | None = None,
        response_blob: str | None = None,
        ts: str | None = None,
    ) -> int:
        ts = ts or utc_now_iso()
        if prompt_text is not None and prompt_blob is None:
            prompt_blob = self.put_blob(prompt_text)
        if response_text is not None and response_blob is None:
            response_blob = self.put_blob(response_text)

        cursor = self._connection.execute(
            """
            INSERT INTO llm_calls (
                ts, agent, chat_id, model, prompt_hash, tokens_in,
                tokens_out, cost, duration_ms, prompt_blob, response_blob
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                agent,
                chat_id,
                model,
                prompt_hash,
                tokens_in,
                tokens_out,
                cost,
                duration_ms,
                prompt_blob,
                response_blob,
            ),
        )
        return int(cursor.lastrowid)

    def log_tool_call(
        self,
        agent: str,
        tool: str,
        params: dict | str = "{}",
        result: dict | str = "{}",
        error: str | None = None,
        chat_id: int | None = None,
        ts: str | None = None,
        duration_ms: int | None = None,
        cycle_id: int | None = None,
        compacted: bool = False,
    ) -> int:
        ts = ts or utc_now_iso()
        params_json = params if isinstance(params, str) else json.dumps(params)
        result_json = result if isinstance(result, str) else json.dumps(result)
        with self.transaction():
            cursor = self._connection.execute(
                """
                INSERT INTO tool_calls (
                    ts, agent, chat_id, tool, params_json, result_json, error,
                    duration_ms, cycle_id, compacted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, agent, chat_id, tool, params_json, result_json, error,
                 duration_ms, cycle_id, int(compacted)),
            )
            call_id = int(cursor.lastrowid)
            if self.event_log:
                chat = self.get_chat(chat_id) if chat_id is not None else None
                self.event_log.append(
                    "tool.called", f"tool:{call_id}",
                    {"id": call_id, "agent": agent, "tool": tool, "chat_id": chat_id,
                     "topic": chat["topic"] if chat else None, "cycle_id": cycle_id,
                     "duration_ms": duration_ms, "success": error is None,
                     "error": error, "ts": ts, "compacted": compacted},
                    actor=agent,
                )
            return call_id

    def log_cli_command(self, command: str, args: dict | str = "{}", ts: str | None = None) -> int:
        ts = ts or utc_now_iso()
        args_json = args if isinstance(args, str) else json.dumps(args)
        cursor = self._connection.execute(
            """
            INSERT INTO cli_commands (ts, command, args_json)
            VALUES (?, ?, ?)
            """,
            (ts, command, args_json),
        )
        return int(cursor.lastrowid)

    # --- Bridge & Briefing Persistence ---

    def create_bridge_conversation(
        self,
        title: str,
        created_ts: str | None = None,
        status: str = "idle",
        archived: bool = False,
    ) -> int:
        ts = created_ts or utc_now_iso()
        with self.transaction():
            cursor = self._connection.execute(
                """
                INSERT INTO bridge_conversations (title, created_ts, updated_ts, status, archived)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, ts, ts, status, int(archived)),
            )
            return int(cursor.lastrowid)

    def get_bridge_conversation(self, conversation_id: int) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM bridge_conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_bridge_conversations(
        self,
        limit: int = 50,
        q: str | None = None,
        archived: bool | None = False,
    ) -> list[dict]:
        query = "SELECT * FROM bridge_conversations WHERE 1=1"
        params: list[Any] = []
        if archived is not None:
            query += " AND archived = ?"
            params.append(int(archived))
        if q and q.strip():
            query += """ AND (
                title LIKE ? OR id IN (
                    SELECT conversation_id FROM bridge_messages WHERE text LIKE ?
                )
            )"""
            pattern = f"%{q.strip()}%"
            params.extend([pattern, pattern])
        query += " ORDER BY updated_ts DESC, id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def update_bridge_conversation(
        self,
        conversation_id: int,
        title: str | None = None,
        status: str | None = None,
        archived: bool | None = None,
        updated_ts: str | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []
        if title is not None:
            sets.append("title = ?")
            params.append(title)
        if status is not None:
            if status not in ("idle", "thinking"):
                raise ValueError(f"Invalid bridge conversation status: {status}")
            sets.append("status = ?")
            params.append(status)
        if archived is not None:
            sets.append("archived = ?")
            params.append(int(archived))
        if updated_ts is not None:
            sets.append("updated_ts = ?")
            params.append(updated_ts)
        else:
            sets.append("updated_ts = ?")
            params.append(utc_now_iso())

        if not sets:
            return

        params.append(conversation_id)
        with self.transaction():
            self._connection.execute(
                f"UPDATE bridge_conversations SET {', '.join(sets)} WHERE id = ?",
                params,
            )

    def append_bridge_message(
        self,
        conversation_id: int,
        author: str,
        kind: str,
        text: str,
        ts: str | None = None,
        context: dict | None = None,
        refs: list | None = None,
        action_id: int | None = None,
    ) -> int:
        if kind not in ("text", "agent_relay", "action", "error"):
            raise ValueError(f"Invalid bridge message kind: {kind}")
        ts = ts or utc_now_iso()
        context_json = json.dumps(context) if context is not None else None
        refs_json = json.dumps(refs) if refs is not None else None
        with self.transaction():
            cursor = self._connection.execute(
                """
                INSERT INTO bridge_messages (
                    conversation_id, author, kind, text, ts, context_json, refs_json, action_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, author, kind, text, ts, context_json, refs_json, action_id),
            )
            msg_id = int(cursor.lastrowid)
            self._connection.execute(
                "UPDATE bridge_conversations SET updated_ts = ? WHERE id = ?",
                (ts, conversation_id),
            )
            return msg_id

    def list_bridge_messages(
        self,
        conversation_id: int,
        limit: int = 100,
        before: int | None = None,
    ) -> list[dict]:
        with self._lock:
            if before is not None:
                rows = self._connection.execute(
                    """
                    SELECT * FROM bridge_messages
                    WHERE conversation_id = ? AND id < ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (conversation_id, before, limit),
                ).fetchall()
                messages = [dict(r) for r in reversed(rows)]
            else:
                rows = self._connection.execute(
                    """
                    SELECT * FROM bridge_messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (conversation_id, limit),
                ).fetchall()
                messages = [dict(r) for r in reversed(rows)]
            return messages

    def get_bridge_message(self, message_id: int) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM bridge_messages WHERE id = ?", (message_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_bridge_action(
        self,
        conversation_id: int,
        command: str,
        payload: dict | str,
        summary: str,
        capital: bool = True,
        status: str = "pending",
        preview: dict | None = None,
        result_reasons: list[str] | None = None,
        created_ts: str | None = None,
    ) -> int:
        ts = created_ts or utc_now_iso()
        payload_json = payload if isinstance(payload, str) else json.dumps(payload)
        preview_json = json.dumps(preview) if preview is not None else None
        result_reasons_json = json.dumps(result_reasons or [])
        with self.transaction():
            cursor = self._connection.execute(
                """
                INSERT INTO bridge_actions (
                    conversation_id, command, payload_json, summary, capital, status,
                    preview_json, result_reasons_json, created_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    command,
                    payload_json,
                    summary,
                    int(capital),
                    status,
                    preview_json,
                    result_reasons_json,
                    ts,
                ),
            )
            return int(cursor.lastrowid)

    def get_bridge_action(self, action_id: int) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM bridge_actions WHERE id = ?", (action_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_bridge_actions(
        self,
        status: str | None = None,
        conversation_id: int | None = None,
        limit: int = 50,
    ) -> list[dict]:
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
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def update_bridge_action(
        self,
        action_id: int,
        status: str,
        result_reasons: list[str] | None = None,
        decided_ts: str | None = None,
        decided_by: str | None = None,
        preview: dict | None = None,
    ) -> None:
        sets = ["status = ?"]
        params: list[Any] = [status]
        if result_reasons is not None:
            sets.append("result_reasons_json = ?")
            params.append(json.dumps(result_reasons))
        if decided_ts is not None:
            sets.append("decided_ts = ?")
            params.append(decided_ts)
        if decided_by is not None:
            sets.append("decided_by = ?")
            params.append(decided_by)
        if preview is not None:
            sets.append("preview_json = ?")
            params.append(json.dumps(preview))
        params.append(action_id)

        with self.transaction():
            self._connection.execute(
                f"UPDATE bridge_actions SET {', '.join(sets)} WHERE id = ?",
                params,
            )

    def subscribe_bridge_relay(
        self,
        agent: str,
        topic: str,
        conversation_id: int,
        ts: str | None = None,
    ) -> None:
        ts = ts or utc_now_iso()
        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO bridge_relay_subscriptions (agent, topic, conversation_id, created_ts)
                VALUES (?, ?, ?, ?)
                """,
                (agent, topic, conversation_id, ts),
            )

    def list_bridge_relay_subscriptions(self, agent: str, topic: str) -> list[int]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT DISTINCT conversation_id FROM bridge_relay_subscriptions
                WHERE agent = ? AND topic = ?
                """,
                (agent, topic),
            ).fetchall()
            return [int(r["conversation_id"]) for r in rows]

    def set_briefing_seen(self, ts: str | None = None) -> str:
        ts = ts or utc_now_iso()
        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO briefing_state (key, value, updated_ts)
                VALUES ('last_seen_ts', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_ts = excluded.updated_ts
                """,
                (ts, ts),
            )
        return ts

    def get_briefing_seen(self) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM briefing_state WHERE key = 'last_seen_ts'"
            ).fetchone()
            return str(row["value"]) if row else None

