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
  - Returns `runtime_version`, `halted`, `db_path`, `broker_stream_connected`, and `timestamp`.
  - Used for Docker container healthcheck and UI status indicator.

### 2.2 Commands (Mutations)
- `POST /v1/commands/{name}`
  - Headers:
    - `Idempotency-Key`: UUID identifying the command execution (prevents duplicates).
    - `X-Actor`: Identity of caller (e.g. `cli`, `cockpit`, `telegram`).
  - Supported commands:
    - `enqueue_task`: Enqueue manual analysis task for an agent on a ticker.
    - `say`: Post a user message to an agent's chat topic (sending to PM automatically schedules a task).
    - `add_watchlist` / `remove_watchlist`: Manage watchlist symbols.
    - `approve_order`: Approve a pending bracket order (requires `confirm: true`).
    - `reject_order`: Reject a pending order with a reason.
    - `halt` / `resume`: Emergency trading halt (blocks all orders) and resume.
    - `reconcile_broker`: Reconcile broker open orders and portfolio positions.
    - `refresh_data`: Trigger data pre-fetch cache refresh (returns HTTP 202).
    - `mark_inbox_read`: Mark system alert inbox item as read.
    - `ingest_alert`: Ingest external alert into PM inbox.
  - Returns: `CommandResult(ok=True/False, command_id=..., reasons=[...], data={...})`.

### 2.3 Read Model (Queries)
- `GET /v1/read/{name}`
  - Read-only SQLite queries running on read-only SQLite connections (`mode=ro`).
  - Supported queries:
    - `/v1/read/health`: System health and status.
    - `/v1/read/portfolio`: Latest portfolio snapshot (equity, cash, buying power, positions).
    - `/v1/read/orders?ticker=&status=&limit=`: List orders with optional filters.
    - `/v1/read/order?id=`: Detailed order with draft and lifecycle events.
    - `/v1/read/trades?ticker=&status=&limit=`: Trade records with entry/exit fills and PnL.
    - `/v1/read/cycles?ticker=&status=&limit=`: Analysis cycles.
    - `/v1/read/cycle?id=`: Specific analysis cycle with full message audit trail.
    - `/v1/read/chat?agent=&topic=&limit=`: Agent chat messages.
    - `/v1/read/ticker_state?ticker=`: Current analysis and state for symbol.
    - `/v1/read/watchlist`: Current watchlist symbols and notes.
    - `/v1/read/inbox?unread_only=&limit=`: System alert notifications.
    - `/v1/read/scheduled_tasks?pending_only=`: Scheduled tasks and timers.

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

## 3. Frontend Integration

The Cockpit frontend connects to:
1. `GET /v1/events?after=0` to hydrate recent state and subscribe to real-time events.
2. `GET /v1/read/*` to load detailed views on navigation.
3. `POST /v1/commands/*` to perform user actions with optimistic UI updates.
