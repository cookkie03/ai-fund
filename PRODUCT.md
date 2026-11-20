# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
React, TypeScript, Vite, Tailwind CSS, shadcn/ui

## Users
Luca, sole owner and operator. The engine trades US equities on Alpaca autonomously, 24/7, across one or more selectable broker accounts. Luca is not a gatekeeper the system waits on: he joins the office as one of its members when he wants to, from desktop or phone.

## Product Purpose
A personal workspace for an autonomous multi-agent LLM trading office. The engine runs 100% on its own; the cockpit is the office itself made visible and inhabitable. Luca can read every agent conversation as it happens, talk in natural language to a dedicated bridge agent that works with all the other agents and with the software itself, and act directly as a person inside the office: brief agents, send or pick news for them, give advice, draw on charts that agents also read and annotate, manage the portfolio, adjust settings, and look into the database, the agents and the office configuration.

## Positioning
Not an approval queue and not a generic trading terminal. It is a shared workspace where a human and autonomous agents work on the same material (charts, news, theses, orders, portfolio) and see each other's marks. Autonomy is the default state; human presence is an optional, first-class participation, never a bottleneck.

## Operating Context
Operates on desktop workstations and responsive displays alongside the Python engine running continuously (Docker/local). Active during US market sessions (NYSE/NASDAQ 09:30–16:00 EST), pre-market preparation, and post-market review. Interfaces with Alpaca broker accounts (each with its own credentials), local SQLite WAL database, and OmniRoute LLM endpoints.

## Capabilities and Constraints
Five pages, one design system:

1. **Assistente**: home. Natural-language conversation with the Bridge agent, Luca's peer: it reads everything, talks to every office agent and uses the same commands Luca has in the UI (capital-touching actions ask for confirmation).
2. **Ufficio**: the agents (list or a better arrangement), each with its chats open to read and write into, and the live stream of the tools it calls. Luca can talk directly to any specialist agent, not only through the Bridge.
3. **Terminale**: one dense page in the manner of professional finance software: chart (TradingView lightweight-charts), quote/order book, open and pending orders (approve or reject when an account runs in manual mode), the agents active on that instrument, and the watchlist shared with the agents, which Luca edits as a "wildcard colleague". Whatever an agent draws on a chart (levels, trend lines, indicators) appears there, and whatever Luca draws the agents can read.
4. **Portafoglio**: portfolio management like a desktop banking app: statistics, how much is invested, allocation, positions, trades, performance; plus a section defining the financial metrics and risk constraints the portfolio must respect.
5. **Configurazioni**: the technical side: agents, models and prompts, schedules, budgets, data providers, broker accounts, database and retention, Runtime health.

Cross-cutting:
- Input from Luca (messages, news, drawings, watchlist edits) is weighed by agents like a senior colleague's view: they may disagree and say why; the Risk Gate stays sovereign.
- Deterministic Risk Gate visible wherever orders appear (1% trade risk, 10% position, 30% sector, 30 positions, 5% cash reserve, R:R >= 1.5, 2-day earnings embargo).
- Inbox of alerts and events (including approvals for manual accounts), reachable from every page.
- Broker accounts: one or more selectable accounts (one Runtime each), active account always visible; no paper/live mode in the UI.
- Explicit states: data freshness, Runtime and broker stream connectivity, halt, empty, loading, error. Zero mock data in production surfaces.
- Tabular numerals, keyboard operability, every page usable on phone.
- Backend: the single-writer Runtime (HTTP /v1, SSE). Still missing there: Bridge agent, shared chart annotations (table, agent tools, events), tool-call stream in events, OHLCV and equity-history reads, editable portfolio constraints and configuration. US equities on Alpaca expose quotes (NBBO) and trades, not full depth: the "order book" is bid/ask plus time and sales unless a depth vendor is added.

## Brand Commitments
- Convention is the commitment: the cockpit looks and behaves like the best software of each kind it contains (professional finance terminal, desktop banking app, assistant chat, agent workspace), executed at full craft, with no metaphor or theme imposed on the pages. Chosen explicitly by Luca on 2026-11-20 after two direction rounds.
- Single dark theme; dense, high-contrast, calm at rest.
- shadcn/ui foundation, 21st.dev for component discovery, Figma for approved references; standard tools, no custom stack.
- Standard financial colour semantics for PnL and order states; motion only for state.

## Evidence on Hand
- `docs/frontend.md`: binding frontend design, trading-specific UX, and quality assurance rules.
- `.scratch/agent-mvp/spec.md`: core system architecture, agent roles, trigger engine, order lifecycle, and risk limits.
- `README.md`: operational commands, Docker deployment, configuration structure, and cycle workflows.
- `config/office.toml`: system parameters, budgets, schedules, and agent endpoints.

## Product Principles
1. **Autonomy First**: the office works without Luca; nothing in the interface implies it is waiting for him unless a real gate (manual account, halt) says so.
2. **Shared Material**: human and agents act on the same objects, and every mark shows who made it, human or which agent.
3. **Truth Over Polish**: every value and state is real and timestamped; stale data is flagged, errors are never masked, mock data is forbidden.
4. **Agent Transparency**: the debate, data and reasoning behind every decision are one step away.
5. **Information Density With Calm**: dense, scannable, tabular; quiet at rest, salient only for real events.

## Accessibility & Inclusion
- Single dark theme, high-contrast, suited for extended trading sessions.
- Monospace tabular numerals (`font-variant-numeric: tabular-nums`) across all financial tables, prices, and metrics.
- Full keyboard operability for navigation, inspection, and order approval/rejection workflows.
