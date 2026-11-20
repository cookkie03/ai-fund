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
- Office workspace: every agent chat and cycle (Portfolio Manager, Market, Sentiment, Technical, Fundamental, Risk), readable live, with the shared state behind each decision.
- Bridge agent: a separate agent Luca talks to in natural language; it collaborates with all office agents and can query and operate the software on his behalf.
- Human as office member: post into agent chats, brief or redirect agents, select and dispatch news, advise, enqueue tasks, manage the watchlist.
- Shared charts: Luca and agents draw and write on the same charts (levels, zones, notes), and each side sees the other's annotations.
- Terminal: charts, open and pending orders, bracket orders, trailing stops, watchlist.
- Portfolio management: equity, cash, positions, trades, risk exposure.
- Inbox: alerts, events and the few items that ask for Luca (including order approvals when an account runs in manual mode).
- Settings and office configuration: agents, schedules, budgets, risk limits, accounts; views onto the database and agent memory.
- Deterministic Risk Gate visible wherever orders appear (1% trade risk, 10% position, 30% sector, 5% cash reserve, R:R >= 1.5, 2-day earnings embargo).
- Controls: halt/resume, reconcile, data refresh; LLM token and cost tracking; database size.
- Broker accounts: one or more selectable accounts, active account always visible; no paper/live mode in the UI.
- Explicit states: data freshness, Runtime and broker stream connectivity, empty, loading, error. Zero mock data in production surfaces.
- Tabular numerals, keyboard operability, usable on phone.
- Backend: the single-writer Runtime (HTTP /v1 commands and reads, SSE events). Bridge agent and shared chart annotations do not exist yet in the backend and must be added there.

## Brand Commitments
- Visual authority: professional trading terminal aesthetic (dense, structured, high-contrast, distraction-free) adhering to `docs/frontend.md`.
- Component foundations: shadcn/ui component system with 21st.dev component discovery; Figma as source of truth for approved design comps.
- Semantic consistency: unambiguous, standard financial color semantics for PnL and order statuses; minimal gratuitous motion or decorative styling.

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
