# Runtime API (Cockpit & Dashboard Backend)

The Trading Agent single-writer Runtime process exposes an HTTP and Server-Sent Events (SSE) API designed to feed the frontend cockpit and external thin clients (CLI, Telegram).

## 1. Architecture

- **Single Writer Process**: One persistent Python process manages the SQLite database (`data/trading-agent.db`) exclusively under an OS-level flock lock (`<db>.lock`).
- **Transport**: FastAPI application serving on `127.0.0.1:8765` by default (`TRADING_AGENT_API_HOST`, `TRADING_AGENT_API_PORT`).
- **Authentication**: When `TRADING_AGENT_API_TOKEN` is configured (or when binding outside loopback), all endpoints require an `Authorization: Bearer <token>` header.
- **Event Bus & Stream**: Internal events (`order.*`, `trade.*`, `cycle.*`, `task.*`, `halt.*`) are recorded transactionally to the append-only `events` SQLite table and broadcast over SSE.

## 2. Endpoints

### 2.1 Health & Diagnostics
- `GET /v1/health`
  - Returns `account_label`, `runtime_version`, `halted`, `broker_configured`, `broker_stream_connected`, `next_scheduler_due_ts`, `db_size_bytes` and `last_event_id`.
  - `account_label` comes from `TRADING_AGENT_ACCOUNT_LABEL` (default `default`). There is one Runtime per broker account, each with its own DB and port, so the label tells a client which account it is talking to. Paper or live is never exposed: it depends only on the account credentials.
  - Used by the Docker healthcheck and by the UI status indicator.

### 2.2 Commands (Mutations)
- `POST /v1/commands/{name}`
  - Headers:
    - `Idempotency-Key`: UUID identifying the command execution (prevents duplicates).
    - `X-Actor`: Identity of caller (e.g. `cli`, `cockpit`, `telegram`).
  - Supported commands:
    - `enqueue_task`: Enqueue manual analysis task for an agent on a ticker.
    - `say`: Post a user message to an agent's chat topic (sending to PM automatically schedules a task).
    - `add_watchlist` / `remove_watchlist`: Manage watchlist symbols. `added_by` is set from `X-Actor`.
    - `upsert_annotation` / `strike_annotation`: Manage chart annotations (shared environment). `strike` marks them as struck without physical deletion.
    - `approve_order`: Approve a pending bracket order (requires `confirm: true`).
    - `reject_order`: Reject a pending order with a reason.
    - `halt` / `resume`: Emergency trading halt (blocks all orders) and resume.
    - `reconcile_broker`: Reconcile broker open orders and portfolio positions.
    - `refresh_data`: Trigger data pre-fetch cache refresh (returns HTTP 202).
    - `mark_inbox_read`: Mark system alert inbox item as read.
    - `ingest_alert`: Ingest external alert into PM inbox.
  - Returns `CommandResult` as JSON: `{"ok": bool, "data": {...}, "reasons": [...]}`. A domain refusal (for example an order that is not pending) is `ok: false` with reasons, not an HTTP error. Validation errors are HTTP 422; unknown commands are 404. Repeating the same `Idempotency-Key` returns the saved result without executing again.

### 2.3 Read Model (Queries)
- `GET /v1/read/{name}`
  - Read-only SQLite queries running on read-only SQLite connections (`mode=ro`).
  - Supported queries:
    - `/v1/read/health`: System health and status.
    - `/v1/read/portfolio`: Latest portfolio snapshot (`ts`, `equity`, `cash`, `positions`).
    - `/v1/read/orders?status=&limit=`: List orders with optional filters.
    - `/v1/read/order?id=`: Detailed order with draft and lifecycle events.
    - `/v1/read/trades?ticker=&status=&limit=`: Trade records with entry/exit fills and PnL.
    - `/v1/read/cycles?ticker=&status=&limit=`: Analysis cycles.
    - `/v1/read/cycle?id=`: Specific analysis cycle with full message audit trail.
    - `/v1/read/chat?agent=&topic=&limit=`: Agent chat messages.
    - `/v1/read/ticker_state?ticker=`: Current analysis and state for symbol.
    - `/v1/read/watchlist`: Current watchlist symbols, notes and author (`added_by`).
    - `/v1/read/bars?ticker=&timeframe=&start=&end=&limit=`: OHLCV bars for lightweight-charts (`time` as UTC epoch s). If omitted, `timeframe` uses `[market].bar_timeframe` in `config/office.toml` (default `1h`).
    - `/v1/read/indicators?ticker=&timeframe=1h&names=ema20,rsi14,atr14,sma20,macd,pivot`: Series aligned with bars.
    - `/v1/read/annotations?ticker=&include_struck=`: Chart annotations (shared environment).
    - `/v1/read/equity_history?from=&to=`: Portfolio equity history.
    - `/v1/read/inbox?unread_only=&limit=`: System alert notifications.
    - `/v1/read/scheduled_tasks?status=&limit=`: Scheduled tasks.

### 2.4 Server-Sent Events (Live Stream)
- `GET /v1/events`
  - Parameters / Headers:
    - `?after=<id>` or `Last-Event-ID: <id>`: Replays past events since event ID, then streams live events in real-time.
  - Event wire format:
    ```
    id: 104
    event: trade.opened
    data: {"trade_id": 1, "ticker": "AAPL", "entry_price": 150.0, "qty": 10.0}
    ```
  - Includes `: ping\n\n` keepalive comments to prevent connection timeouts.
  - New event types: `annotation.created`, `annotation.updated`, `annotation.struck`.

## 3. Frontend Integration

The Cockpit frontend connects to:
1. `GET /v1/events?after=0` to hydrate recent state and subscribe to real-time events.
2. `GET /v1/read/*` to load detailed views on navigation.
3. `POST /v1/commands/*` to perform user actions with optimistic UI updates.

### 3.1 Browser constraints (current state)

- The Runtime has **no CORS middleware**. A browser app served from another origin (for example the Vite dev server) reaches the API through a same-origin proxy or needs CORS added to the Runtime.
- The browser `EventSource` cannot send an `Authorization` header. On loopback without `TRADING_AGENT_API_TOKEN` this is not needed; with a token, the event stream needs another mechanism (for example a proxy that adds the header).
- Multiple accounts: each Runtime has its own URL, and the UI selects an account by selecting the Runtime URL. There is no registry of Runtimes in the backend.
- Development without a broker or LLM: run `uv run python scripts/dev_cockpit_server.py --port 8766 --db data/dev-cockpit.db` (options: `--approval-mode manual|auto`). It recreates the database on every start and seeds a realistic scenario from `scripts/dev_cockpit_scenario.py`: deterministic NYSE 15m bars for a fixed set of tickers (unknown symbols return no bars), a watchlist with mixed authors, signed annotations, orders in every state, open and closed trades, equity history, agent analyses and inbox items. It uses `build_test_office` and `Runtime`. Development only: never point a production cockpit at it.
- Frontend: `cd frontend && npm install && npm run dev`. Vite serves on `COCKPIT_PORT` (default 5174) and proxies `/v1` to `COCKPIT_RUNTIME_URL` (default `http://127.0.0.1:8766`), because the Runtime has no CORS. Extra accounts come from `VITE_COCKPIT_RUNTIMES` (JSON list of `{id, label, url}`). The visual system is in `DESIGN.md`.

