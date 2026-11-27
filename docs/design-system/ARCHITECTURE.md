# Architecture: one design-system folder, pages only compose

Everything visual lives in one folder of the frontend. Pages contain no styling decisions of their own: they import and arrange pieces from it, so a change to a button, a block or a colour happens in exactly one place.

## Folder

```
frontend/src/
  ds/                         ← the design system, the only place UI is defined
    theme/
      tokens.css              ← :root / .dark colour variables, radius (this system's tokens.json)
      typography.css          ← balance, page-title, figure, section-title, body, label, caption
      motion.css              ← easing tokens and motion utilities (ds-reveal, ds-flash-*, ds-breathe, ds-grow-x, ds-lift)
      index.css               ← @import "tailwindcss", tw-animate, shadcn/tailwind.css, the two files above
    ui/                       ← vanilla shadcn/ui on Base UI, added with the CLI, never hand-edited
    identity/                 ← AgentAvatar, AfMark, Delta, StatusBadge
    motion/                   ← Reveal, AnimatedNumber, PriceFlash
    blocks/
      shell/                  ← AppSidebar, TopBar, FreshnessBadge, HaltButton, MobileTabBar, AssistantSheet
      pages/                  ← PageHeader, HeroBalance, StatCard
      portfolio/              ← PositionsTable, OrdersTable, LimitBar, AllocationList, EquityChart
      approvals/              ← ProposalCard, DecideDialog
      markets/                ← MarketsWorkspace, Watchlist, AuthorFilter
      agents/                 ← AgentCard, AgentTree, ToolCallRow, ActivityFeed, ChatThread, Composer
    charts/                   ← grayscale Chart wrappers + TradingViewChart (wrapper only: never restyled)
    icons/index.ts            ← the Lucide icons the app uses, re-exported by name
    lib/                      ← cn, formatters (money, percent, dates, en-US)
    index.ts                  ← the public surface: pages import from "@/ds" only
  pages/                      ← routes: compose blocks, fetch data, no classNames beyond layout
  features/                   ← data hooks and Runtime calls, no UI
```

## Rules

- `components.json` points shadcn's `ui` alias at `@/ds/ui`; components arrive with `npx shadcn add` (Base UI base, `base-vega` style, neutral, Lucide) and stay vanilla. Customisation happens by composing them in `identity/` or `blocks/`, not by editing `ui/`.
- **No Radix.** Only `@base-ui/react` primitives. A shadcn component that pulls Radix in (cmdk's Command) is replaced by its Base UI equivalent (Combobox).
- Pages may use layout utilities (`grid`, `gap-6`, `col-span-*`) and nothing else; colours, radii, type sizes and shadows come from components.
- Colour values exist only in `ds/theme/tokens.css`; a hex or oklch literal anywhere else is a bug.
- The author sign exists only in `ds/identity/agent-avatar.tsx`; icons only through `ds/icons`.
- The TradingView chart lives in `ds/charts/` as a wrapper that passes data through and keeps the library's own styling.
- In this design system the same pieces are bundled from `src/components/ui` (shadcn) and `src/components/fund` (identity, motion, blocks); the tree above is where they go in the app.
- This design system mirrors that folder: `tokens.json` = `theme/`, the component cards = `ui/` + `identity/` + `blocks/`.
