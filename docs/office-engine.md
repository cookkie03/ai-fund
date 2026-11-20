# Agent Office Engine — Operating Guide

Operating manual for the autonomous Agent Office engine and CLI.

## 1. Running in Development (uv)

Start the single-writer Runtime process (event-driven scheduler + HTTP/SSE API server):
```bash
uv run trading-agent run
```

Run CLI subcommands directly from another terminal (the CLI operates as a thin client against `http://127.0.0.1:8765` or `--runtime URL`):
```bash
# Verify configuration (local command, does not require Runtime)
uv run trading-agent config check

# Create a manual Scheduled task on a ticker
uv run trading-agent task AAPL --reason "Catalyst review"

# Write directly into an agent's chat (a message to PM triggers a task)
uv run trading-agent say portfolio_manager AAPL "Prioritize valuation check"

# Inspect cycles, chats, state, and watchlist
uv run trading-agent cycles list
uv run trading-agent cycles show 1
uv run trading-agent chat show portfolio_manager AAPL
uv run trading-agent state show AAPL
uv run trading-agent watchlist list
uv run trading-agent watchlist add NVDA --note "AI semiconductor"

# Inspect orders and trades
uv run trading-agent orders list
uv run trading-agent trades list

# Sync portfolio and refresh cache
uv run trading-agent portfolio sync
uv run trading-agent data refresh AAPL MSFT --force

# Inspect alert inbox
uv run trading-agent inbox
```

## 2. Running in Docker (Production / Home Server)

Deploy with Docker Compose:
```bash
# Build and start engine service
docker compose -f compose.engine.yaml up -d

# Check engine logs
docker compose -f compose.engine.yaml logs -f engine

# Execute CLI commands inside the running container
docker compose -f compose.engine.yaml exec engine uv run trading-agent cycles list
```

Data and SQLite database persist in the `trading-agent-data` named volume (`/app/data/trading-agent.db`).

## 3. Configuration Files

- `.env`: Holds secrets, API keys, and endpoint variables:
  - `OMNIROUTE_API_KEY`: LLM gateway key
  - `ALPACA_API_KEY` & `ALPACA_SECRET_KEY`: Broker paper credentials
  - `TRADING_AGENT_DB`: Custom SQLite database path (default: `data/trading-agent.db`)
- `config/office.toml`: Engine parameters, agent reasoning effort levels (`low`, `medium`, `high`), Risk Gate limits, budgets, schedule, and retention rules.

Verify configuration validity at any time:
```bash
uv run trading-agent config check
```

## 4. Approval Modes

Configured via `approval_mode` in `config/office.toml` (`auto` or `manual`):
- `auto`: Accepted orders pass Risk Gate and are automatically submitted to the broker.
- `manual`: Accepted orders queue in `pending` approval status. Approve or reject via CLI:
  ```bash
  # Approve order (re-checks draft hash & Risk Gate)
  uv run trading-agent orders approve <order_id>

  # Reject order (creates Deferral in PM chat)
  uv run trading-agent orders reject <order_id> --reason "Market volatility too high"
  ```

## 5. Emergency Halt & Resume

Stop all trading operations and trigger engine immediately:
```bash
# Halt and cancel open orders
uv run trading-agent halt --cancel-open

# Halt without cancelling existing open bracket orders
uv run trading-agent halt --no-cancel-open

# Resume normal operations
uv run trading-agent resume
```
All halt/resume actions, commands, and order lifecycle changes are permanently logged in the append-only `events` table and in `inbox`.
