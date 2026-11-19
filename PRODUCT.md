# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
React, TypeScript, Vite, Tailwind CSS, shadcn/ui

## Users
Luca (operator, portfolio manager, supervisor). Sole trader overseeing an autonomous US equity trading engine operating 24/7 on Alpaca, across one or more selectable broker accounts.

## Product Purpose
A high-density operational trading terminal and supervisor cockpit for an autonomous multi-agent LLM trading office. Enables full visibility into agent deliberation cycles (Portfolio Manager, Market, Sentiment, Technical, Fundamental, and Risk Analysts), real-time portfolio and bracket order monitoring, manual order review and approval, deterministic risk gate transparency, and system telemetry.

## Positioning
An industrial-grade trading terminal engineered specifically for overseeing collaborative AI agents governed by deterministic financial guardrails. Unlike generic SaaS analytics dashboards or consumer retail apps, it delivers information-dense, latency-conscious situational awareness where LLM strategy meets hard risk limits and real broker execution.

## Operating Context
Operates on desktop workstations and responsive displays alongside the Python engine running continuously (Docker/local). Active during US market sessions (NYSE/NASDAQ 09:30–16:00 EST), pre-market preparation, and post-market review. Interfaces with Alpaca broker accounts (each with its own credentials), local SQLite WAL database, and OmniRoute LLM endpoints.

## Capabilities and Constraints
- Operational cockpit: real-time visibility into agent chat cycles, individual analyst rationales, and consensus decisions.
- Order management: approval queue for manual approval mode, bracket order inspection (entry, take-profit, stop-loss), trailing stop progression, and Alpaca broker synchronization.
- Deterministic Risk Gate: clear visualization of two-tier risk limits (max 1% trade risk, 10% position limit, 30% sector limit, min 5% cash reserve, R:R >= 1.5, 2-day earnings embargo).
- Telemetry & controls: emergency kill switch / halt command, scheduled task queue, LLM token and cost tracking, database size monitoring.
- Broker accounts: one or more selectable accounts; the active account is always visible. No paper/live mode in the UI: an account is paper or live only by its credentials.
- Explicit states: unambiguous display of market data freshness, network connectivity, empty states, and errors. Zero mock or simulated data in production surfaces.
- Tabular financial numerals and keyboard navigation for rapid scanning and order approvals.

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
1. **Truth Over Polish**: Every value, timestamp, and connection state reflects real system facts; stale data is explicitly flagged, errors are never masked, and mock data is strictly forbidden.
2. **Information Density First**: Engineered for rapid high-signal scanning; zero decorative padding, optimal contrast, and tabular typography.
3. **Explicit Risk and Execution**: Order state transitions, risk gate blocks, trailing stops, and manual approval gates must be obvious and instantaneous to interpret.
4. **Agent Transparency**: Complete explainability of LLM decision-making by exposing the debate, technical indicators, and reasoning chains behind every proposed trade.
5. **Operational Restraint**: Visual hierarchy exists to protect capital and accelerate decision-making, not to entertain; quiet resting state with crisp, high-salience alerts for critical events.

## Accessibility & Inclusion
- Single dark theme, high-contrast, suited for extended trading sessions.
- Monospace tabular numerals (`font-variant-numeric: tabular-nums`) across all financial tables, prices, and metrics.
- Full keyboard operability for navigation, inspection, and order approval/rejection workflows.
