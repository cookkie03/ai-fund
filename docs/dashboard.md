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
    - `update_risk_limits`, `close_position`, `modify_exit`: see §2.5 (Portafoglio).
  - Returns `CommandResult` as JSON: `{"ok": bool, "data": {...}, "reasons": [...]}`. A domain refusal (for example an order that is not pending) is `ok: false` with reasons, not an HTTP error. Validation errors are HTTP 422; unknown commands are 404. Repeating the same `Idempotency-Key` returns the saved result without executing again.

### 2.3 Read Model (Queries)
- `GET /v1/read/{name}`
  - Read-only SQLite queries running on read-only SQLite connections (`mode=ro`).
  - Supported queries:
    - `/v1/read/health`: System health and status.
    - `/v1/read/agents`: Configured agents (`config/office.toml` & DB) with `name`, `role`, `model`, `status` (`working` | `waiting` | `idle`), `current_task` (`ticker`, `cycle_id` or `task_id`), `last_activity_ts`, `today_tokens_in`, `today_tokens_out`, `today_tokens`, and `today_cost`.
    - `/v1/read/chat_topics?agent=`: Chat topics for an agent with `id`, `topic`, `title`, `ticker`, `cycle_id`, `message_count`, `last_activity_ts`, and `last_message` preview.
    - `/v1/read/tool_calls?agent=&cycle=&after=&limit=`: Audit trail of tool calls with tool name, `params`, `result`, `duration_ms`, `success`, `error`, `chat_id`, `topic`, `cycle_id`, `ts`, and explicit `compacted` boolean flag (true if pruned by retention, false otherwise).
    - `/v1/read/usage?agent=&from=&to=`: Aggregated LLM token usage and cost from `llm_calls` grouped by agent and filtered by ISO UTC date range (`from`, `to`).
    - `/v1/read/portfolio`: Latest portfolio snapshot (`ts`, `equity`, `cash`, `positions`).
    - `/v1/read/orders?status=&limit=`: List orders with optional filters.
    - `/v1/read/order?id=`: Detailed order with draft and lifecycle events.
    - `/v1/read/trades?ticker=&status=&limit=`: Trade records with entry/exit fills and PnL. Besides the stored fields each trade has `pnl` (realized; open: null), `r_multiple`, `duration_s`, `proposed_by`, `exit_reason`, `stop_price`, `target_price`, `qty_remaining` (see §2.5).
    - `/v1/read/cycles?ticker=&status=&limit=`: Analysis cycles.
    - `/v1/read/cycle?id=`: Specific analysis cycle with full message audit trail.
    - `/v1/read/chat?agent=&topic=&limit=`: Agent chat messages: the most recent `limit` messages, oldest first.
    - `/v1/read/ticker_state?ticker=`: Current analysis and state for symbol.
    - `/v1/read/watchlist`: Current watchlist symbols, notes and author (`added_by`).
    - `/v1/read/bars?ticker=&timeframe=&start=&end=&limit=`: OHLCV bars for lightweight-charts (`time` as UTC epoch s). If omitted, `timeframe` uses `[market].bar_timeframe` in `config/office.toml` (default `1h`).
    - `/v1/read/indicators?ticker=&timeframe=1h&names=ema20,rsi14,atr14,sma20,macd,pivot`: Series aligned with bars.
    - `/v1/read/annotations?ticker=&include_struck=`: Chart annotations (shared environment).
    - `/v1/read/equity_history?from=&to=`: Portfolio equity history; every point also has `drawdown_fraction` (<= 0, versus the running peak of the returned range).
    - `/v1/read/portfolio_summary`, `positions`, `allocation`, `performance`, `attribution`, `risk_limits`, `risk_limits_history`: Portafoglio page, see §2.5.
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
  - Live office events:
    - `chat.message`: Message appended to an agent's chat topic (`chat_id`, `message_id`, `agent`, `topic`, `author`, `text`, `kind`, `cycle_id`, `ts`).
    - `tool.called`: Tool invocation recorded with execution outcome and duration (`id`, `agent`, `tool`, `chat_id`, `topic`, `cycle_id`, `duration_ms`, `success`, `error`, `ts`, `compacted`).
    - `agent.status`: Agent status change (`agent`, `status` in `working` | `waiting` | `idle`, `current_task`, `ts`).
  - Terminal & chart event types: `annotation.created`, `annotation.updated`, `annotation.struck`.
  - Portafoglio events (published only after the transaction commits, never on rollback): `portfolio.updated` (`reason`, `ticker`), `position.changed` (`ticker`, `trade_id`, `change` in `opened` | `reduced` | `closed` | `exit_levels` | `trailing_stop`, `qty_remaining`, `stop_price`, `target_price`), `risk_limits.updated` (`version`, `updated_by`, `reason`, `before`, `after`, `limits`), plus the existing `order.created`, `order.status_changed`, `trade.opened`, `trade.closed` and the new `trade.reduced` (partial close: `trade_id`, `ticker`, `qty`, `price`, `ts`). `portfolio.updated` is emitted by trade opens/reduces/closes and by `reconcile_broker` (which also keeps emitting `portfolio.synced`).

### 2.5 Portafoglio (read model, commands, formulas)

Conventions: amounts are numbers in the account currency, percentages are fractions (`0.25` = 25%), timestamps are ISO UTC. Weights are relative to the equity of the latest snapshot.

**Reads**
- `portfolio_summary`: `{ts, equity, cash, invested, cash_reserve_fraction, day_change, day_change_fraction, unrealized_pnl, realized_pnl_today, positions_count, snapshot_age_s, halted}`. `day_change` is the equity versus the last snapshot before today's UTC midnight. With no snapshot every amount is 0 and `ts`/`snapshot_age_s` are null.
- `positions`: list of `{ticker, side, qty, avg_entry_price, current_price, market_value, weight, unrealized_pnl, unrealized_pnl_fraction, stop_price, target_price, open_risk, open_risk_fraction, sector, opened_ts, days_held, trade_id, proposed_by}`. Open trades joined with the prices of the latest snapshot (fallback: last 1d close, then entry price). `qty` is the remaining quantity after partial closes. A broker position without a local trade is listed with null stop/target/`trade_id`; a snapshot position whose trade was closed after the snapshot is not listed. `open_risk = max(price - stop, 0) * qty`.
- `allocation`: `{by_sector:[{sector,value,weight,limit}], by_position:[{ticker,value,weight,limit}], cash:{value,weight,min_reserve}}`; limits are the active `max_sector_fraction`, `max_position_fraction`, `min_cash_reserve_fraction`. Unknown sector = `"Unknown"`.
- `performance?period=1D|1W|1M|3M|YTD|1Y|ALL&benchmark=SPY`: `{period, from, to, observations, return_fraction, realized_pnl, unrealized_pnl, max_drawdown_fraction, current_drawdown_fraction, volatility_annualized, sharpe, sortino, win_rate, profit_factor, expectancy, expectancy_r, trades_closed, benchmark:{ticker,return_fraction,beta,correlation}|null, insufficient:[{metric,reason,min_observations}]}`. Unknown `period` is HTTP 422. A metric without enough data is `null` and listed in `insufficient`; the benchmark is `null` when there are no daily bars (`prices_ohlcv`, interval `1d`).
- `attribution?period=`: `{by_position:[{ticker,pnl,contribution_fraction}], by_sector:[...], by_agent:[{agent,pnl,contribution_fraction,trades}]}`. PnL = closed trades in the window (partial closes included) + unrealized PnL of open positions; `contribution_fraction = pnl / equity at the start of the window`; agent `unknown` when the proposer was not recorded.
- `risk_limits`: `{version, updated_ts, updated_by, limits:{...}, bounds:{name:{min,max}}, usage:[{limit,current,threshold,status:"ok"|"near"|"breach",detail}]}`. Version 0 is virtual: the defaults of `[limits]` in `config/office.toml`. `near` means above 80% of the threshold (for the minimum-cash limit: the reserve is within 20% of the minimum). `usage` covers position size, sector, open positions, minimum cash, worst risk per trade and worst R:R at entry (earnings embargo has no usage).
- `risk_limits_history?limit=`: `[{version, ts, actor, reason, before, after}]`, newest first; `before`/`after` contain only the changed limits.

**Metric formulas** (`analysis/portfolio_metrics.py`, risk-free rate 0, 252 trading days). Equity points are reduced to the last point of each UTC day inside the window (plus the last point at or before the window start).
- `return_fraction = last / first - 1`; daily return `r_t = v_t / v_(t-1) - 1`.
- Drawdown `dd_t = v_t / max(v_0..v_t) - 1`; `max_drawdown_fraction = min(dd)`, `current_drawdown_fraction = dd_last`.
- `volatility_annualized = stdev(r, ddof=1) * sqrt(252)`; `sharpe = mean(r) / stdev(r, ddof=1) * sqrt(252)`; `sortino = mean(r) / sqrt(mean(min(r, 0)^2)) * sqrt(252)`.
- `win_rate = trades with pnl > 0 / trades`; `profit_factor = sum(gains) / sum(|losses|)` (null with no losses); `expectancy = mean(pnl)`; `expectancy_r = mean(R)`, with `R = pnl / ((entry - initial_stop) * qty)` (trades without `initial_stop` are excluded from R).
- Benchmark: `return_fraction` over the same window; `beta = cov(r_p, r_b) / var(r_b)` and `correlation = corr(r_p, r_b)` on date-aligned daily returns.
- Minimum data (below it: `null` + `insufficient`): volatility 10 daily observations; Sharpe, Sortino, beta, correlation 20; win rate, profit factor, expectancy, expectancy in R 5 closed trades.

**Commands** (all need `Idempotency-Key` and `X-Actor`; `{ok, data, reasons}`; `confirm: true` is required unless `dry_run`, otherwise HTTP 422)
- `update_risk_limits {limits:{partial}, reason, confirm}`: validates every value against `bounds`, requires a non-empty `reason`, rejects a no-op, writes version N+1 to `risk_limits_versions` (actor, reason, before, after), one Inbox entry (`risk_limits_updated`) and the `risk_limits.updated` event. The Risk Gate reads the active version on every evaluation (no restart); open positions are not touched. Refusal: `ok:false` with a reason per violation. Bounds (min..max): `max_risk_per_trade_fraction` 0.001..0.05, `max_position_fraction` 0.01..0.25, `max_sector_fraction` 0.05..0.60, `max_open_positions` 1..100, `min_cash_reserve_fraction` 0..0.50, `min_risk_reward_ratio` 1..10, `earnings_embargo_days` 0..10.
- `close_position {ticker, qty|null, order_type:"market"|"limit", limit_price|null, dry_run, confirm}`: `qty` null closes everything that remains; a `limit` order needs `limit_price`. Refused (`ok:false`) when the system is halted, there is no open position, `qty` exceeds the remaining quantity, or the broker raises. It creates a `sell` order (`approval_status: approved`, `client_order_id: close-<ticker>-...`) and asks the broker to sell and keep the residual protected. A fill known at once (fake broker) is recorded immediately; otherwise the broker stream's fill is applied by `apply_broker_update` (local sell orders are `pm_sell`; a quantity below the remaining one is a partial close). Exit reason of a manual close: `pm_sell`. `data` = preview fields + `order:{order_id, client_order_id, broker_order_id, status, side, order_type, qty}`.
- `modify_exit {ticker, stop_price|null, target_price|null, dry_run, confirm}`: stop must be positive and below the current price, target above it, stop below target. Tightening the stop (or changing only the target) is always allowed, also in Halt (protective). Widening the stop recomputes the open risk and runs the Risk Gate per-trade risk check; a violation is `ok:false` with `reasons`. It updates the protective order on the broker (`modify_stop` / `modify_take_profit`), the trade (`stop_price`, `target_price`), the trailing state and emits `position.changed` (`exit_levels`).
- `dry_run: true` on `close_position` / `modify_exit` returns `ok:true` with `data:{dry_run:true, ...}` and `risk_gate:{allowed, reasons}` and performs no write and no event. Close preview: `qty`, `qty_remaining_after`, `reference_price`, `estimated_value`, `estimated_realized_pnl`, `closes_position`. Modify preview: `stop_price`, `target_price`, `previous_*`, `widening_stop`, `tightening_stop`, `open_risk_before`, `open_risk`, `open_risk_fraction`.

**Real-broker note**: `close_position` on `AlpacaBracketAdapter` (cancel the stop/take-profit legs, market or limit sell, OCO on the residual quantity) is only covered with a fake Alpaca client; it has not been verified on a paper account.

## 3. Frontend Integration

The Cockpit frontend connects to:
1. `GET /v1/events?after=0` to hydrate recent state and subscribe to real-time events.
2. `GET /v1/read/*` to load detailed views on navigation.
3. `POST /v1/commands/*` to perform user actions with optimistic UI updates.

### 3.1 Browser constraints (current state)

- The Runtime has **no CORS middleware**. A browser app served from another origin (for example the Vite dev server) reaches the API through a same-origin proxy or needs CORS added to the Runtime.
- The browser `EventSource` cannot send an `Authorization` header. On loopback without `TRADING_AGENT_API_TOKEN` this is not needed; with a token, the event stream needs another mechanism (for example a proxy that adds the header).
- Multiple accounts: each Runtime has its own URL, and the UI selects an account by selecting the Runtime URL. There is no registry of Runtimes in the backend.
- Development without a broker or LLM: run `uv run python scripts/dev_cockpit_server.py --port 8766 --db data/dev-cockpit.db` (options: `--approval-mode manual|auto`). It recreates the database on every start and seeds a realistic scenario from `scripts/dev_cockpit_scenario.py`: deterministic NYSE 15m bars for a fixed set of tickers (unknown symbols return no bars), a watchlist with mixed authors, signed annotations, orders in every state, open and closed trades, equity history, agent analyses and inbox items. For the Portafoglio page it also seeds 6 open positions on 4 sectors (Technology near its sector limit) with stop and target, ~26 closed trades over a year (all exit reasons, different proposing agents), ~1 year of daily equity correlated with daily SPY bars, one risk-limits change in the history, and a fake broker that executes `close_position` / `modify_exit` (`tests/fakes/bracket_broker.py`, never production). It uses `build_test_office` and `Runtime`. Development only: never point a production cockpit at it.
- Frontend: `cd frontend && npm install && npm run dev`. Vite serves on `COCKPIT_PORT` (default 5174) and proxies `/v1` to `COCKPIT_RUNTIME_URL` (default `http://127.0.0.1:8766`), because the Runtime has no CORS. Extra accounts come from `VITE_COCKPIT_RUNTIMES` (JSON list of `{id, label, url}`). The visual system is in `DESIGN.md`.

