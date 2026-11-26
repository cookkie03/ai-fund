# `src/ds` — the AI Fund design system in code

The only place UI is defined. Pages import from `@/ds` and only arrange pieces (layout utilities like `grid`, `gap-6`, `col-span-*`).

- `theme/index.css` — tokens (light + dark), success/warning, radius 14 px, motion utilities. Becomes the app's stylesheet when the shell migrates (import it in `main.tsx` instead of `src/index.css`).
- `ui/` — vanilla shadcn/ui on Base UI (`base-vega`), added with `npx shadcn add` (components.json points here). Never hand-edit; compose instead.
- `identity/` — `AgentAvatar`, `AfMark`, `Delta`, `StatusBadge`.
- `motion/` — `Reveal`, `AnimatedNumber`, `PriceFlash`.
- `blocks/` — shell (AppSidebar, TopBar, FreshnessBadge, HaltButton, MobileTabBar), page (PageHeader, HeroBalance), StatCard, proposals (ProposalCard, DecideDialog), tables (PositionsTable, OrdersTable), risk (LimitBar, AllocationList), charts (EquityChart, TradingViewChart, AuthorFilter), markets (MarketsWorkspace, Watchlist), agents (AgentCard, AgentTree, ToolCallRow, ActivityFeed), chat (ChatThread, Composer).
- `icons/` — the Lucide icons the app uses; import from here.

Status: added alongside the current UI (`src/components`, `src/index.css`), not wired in yet. Pages move over one by one after their ex-ante drawings; then `src/components/ui` and the old tokens go.
