A complete dashboard for an AI-run investment fund with one human, Luca, who supervises autonomous agents: one Portfolio Manager, one Risk Manager, a set of market specialists (technical, market, sentiment, fundamental) and one agent per topic, ticker, company or bond.

**North star: a banking app with a professional engine.** The surface is as simple to navigate as Revolut or Trade Republic — one clear job per page, big readable figures, calm grays — while every professional capability (orders, limits, analyses, agent logs) stays one step away, never on top of everything else.

## Principles

- **One job per page.** Every page answers one question first (How is the fund doing? What needs my approval? What does this agent do?). Its hero figure or list leads; everything else is secondary.
- **Progressive disclosure.** Detail opens on demand: a `Sheet` beside a list, `Tabs` inside an object, a `Dialog` for a task, a `Popover` for a definition or a quick action (switch, open a link, edit in place, accept). Never show all panels at once.
- **One card = one object or one question.** Group with `Card` and a `CardTitle`; if two things need different titles, they are two cards.
- **Distinguishable by shape, not by colour.** Views (charts, tables, lists), objects (instrument, order, agent) and features (approve, halt, edit limits) each have their own component, so the eye can tell them apart in grays.
- **Signed marks.** Every order, message, analysis and drawing shows its author with `AgentAvatar`.

Inspiration, in this order: [ui.shadcn.com](https://ui.shadcn.com) for components and blocks, [pro.shadcn.co](https://pro.shadcn.co) for sidebar, dashboard and app blocks, [shadcn.io](https://www.shadcn.io) for themes and patterns; Revolut and Trade Republic for tone and navigation. Not financial terminals.

## Content

- The UI is in **English**, short and literal. Verbs on buttons: Approve, Approve & send, Postpone, Reject, Decide, Send, Cancel. Page titles are nouns: Home, Portfolio, Approvals, Agents, Markets, News, Assistant, Settings, and an instrument's symbol. The full Italian → English glossary is in DECISIONS.
- Numbers use **en-US** formats: `$1,234.56`, `−2.07%` (true minus sign), grouping always on. Every number that changes or is compared uses tabular numerals and is right-aligned in tables.
- **Currency:** totals and tables in the base currency (USD); an instrument's own price and value also in its native currency (EUR bonds, European equities) on its row and page.
- **Time:** relative under 24 h ("2 min ago"), then `Nov 26, 14:32`.
- Freshness is stated with its age: **Live**, **Connecting…**, **Stale data · 4 min**, **Runtime unreachable**, **Stopped for 2 min**.
- A disabled command says why in its tooltip: *Trading halted*, *Runtime unreachable*. A refusal from the Runtime is shown **verbatim** inside the dialog that caused it.
- States are an icon or dot **and** a word, never colour alone: Within / Near / Over limit; Working / Waiting / Idle; Pending approval / Filled / Rejected / Cancelled.
- Never show sample or invented figures; dev fixtures carry a **Sample data** badge. No emoji.

## Colour

Vanilla shadcn **neutral**, light and dark, monochrome. Colour is spent only on direction and alarms.

- **Grays do the structure.** `background` is the page; `card` sections sit on it with a 1 px ring (foreground at 10%); `popover` carries menus and dialogs; `muted` fills quiet things (agent avatars, skeletons, hover rows); `border` and `input` draw dividers and fields.
- **Two text grays.** `foreground` for primary text and figures, `muted-foreground` for labels, metadata and timestamps. Nothing lighter carries text.
- **No brand hue.** `primary` is near-black in light and near-white in dark: the one committing button and Luca's avatar. Focus uses the gray `ring`.
- **Up and down.** `success` (sober green) for gains, buy and filled; `destructive` (red) for losses, sell, Halt, Reject and breached limits — always with a +/− sign, arrow or icon (`Delta`, `StatusBadge`).
- **Attention.** `warning` (amber) for stale data, pending approval, near a limit and an agent waiting.
- **Charts are grayscale.** `chart-1` (lightest) to `chart-5` (darkest); series differ by lightness, up/down colour only the overall return. **The TradingView chart is never restyled**: it keeps its own colours wherever it appears.
- Known gaps kept from shadcn: `muted-foreground` on `muted` is 4.3:1 in light; the gray `ring` is 2.6:1 on white (it is paired with a border change).

## Type

Inter Variable, tabular numerals for figures.

- `balance` — 36 px / 600: the one hero figure of a page (total equity, a position's value).
- `page-title` — 24 px / 600; `figure` — 24 px / 600 for `StatCard` values.
- `section-title` — 16 px / 500: `CardTitle`.
- `body` — 14 px: default UI text. `label` — 14 px / 500: labels, buttons, menu items.
- `caption` — 12 px in `muted-foreground`: metadata, timestamps, helper text. `mono` for tool names and JSON.

## Layout

- **Shell:** `AppShell` — `AppSidebar` in the **inset** variant (collapsible to icons) and a `SidebarInset` that starts with `TopBar`: sidebar toggle, breadcrumb, instrument search (⌘K), `FreshnessBadge`, Bridge, notifications, `HaltButton`.
- **Accounts:** one account = one broker account, named by Luca. The software never knows whether it is paper or live and never shows that as a state; the sidebar header shows the account name with the account switcher.
- **Navigation:** Home · Portfolio · Approvals (count) · Agents · Markets · News · Assistant, Settings in the footer, Luca's avatar menu (theme, settings). **Home** is the landing page.
- **Bridge:** its own Assistant page for long conversations, and the same chat in a right `Sheet` from the top bar on every page.
- **Pages:** `PageHeader` → hero (`HeroBalance` or three to four `StatCard`s) → cards in a 12-column grid with `gap-6` (`space-section`) and `p-6` page padding.
- **Markets** is the one pro workspace: resizable panels (`MarketsWorkspace`) — watchlist | TradingView chart | agents & drawings, over orders.
- **Density:** shadcn default sizes everywhere; tables of positions, orders and tool calls use compact 32 px rows and `Card size="sm"`.
- **Phones:** `MobileTabBar` — Home · Portfolio · Approvals · Agents · More; one column of cards; detail in a bottom `Drawer`.
- Spacing is Tailwind's 4 px step (`spacing`); cards pad 24 px (`space-card`).

## Shape and depth

- One radius knob, `radius` **14 px** (soft, banking-app): buttons and inputs `rounded-md` (≈11), cards `rounded-xl` (≈20), badges and avatars full.
- Cards carry a 1 px ring and `shadow-xs`; popovers and dialogs a ring and a soft shadow. No gradients, no glass.

## Motion

Everything moves, gently — arrivals, changes, hover — so the eye follows what changed.

- Cards, rows and headers rise in (`Reveal`, 420 ms on `ease-settle`, 60 ms stagger). Figures count up (`AnimatedNumber`, 600 ms). Bars grow from the left (620 ms).
- A price that changes flashes once in a soft `success` / `destructive` tint (900 ms, `ease-out-quint`).
- Interactive cards lift 2 px on hover (`ds-lift`); buttons press 1 px.
- The Working status dot breathes (2.4 s); Connecting breathes too. Nothing else loops.
- shadcn's own enter/exit animations for dialogs, sheets, menus and popovers stay.
- `prefers-reduced-motion` removes movement; the price flash stays because it carries information.

## Iconography

- **Lucide** (`lucide-react`), the default of shadcn/ui, shadcn/ui Pro and shadcn.io. 16 px in buttons, menus and sidebar items, 14 px inside `Delta` and badges, stroke 2, `currentColor`.
- Icons come from one module (`src/ds/icons`), never imported ad hoc in pages.
- The mark is `AfMark`: "AF" in a `primary` rounded square (`assets/Logos/af-mark.svg`, `af-mark-dark.svg` for dark grounds).

## Identity

- `AgentAvatar` is the only author sign: a contact-style circle with initials. Luca solid `primary`, agents `muted`, system outlined; status as a small dot (success working, warning waiting, gray idle). No per-author colours anywhere.

## Do and don't

- Do lead every page with one figure or one list, and push the rest behind tabs, sheets and dialogs.
- Do keep exactly one `default` (primary) button in view.
- Do disable commands while the Runtime is unreachable or trading is halted, and say why.
- Don't colour anything that is not direction or an alarm.
- Don't restyle the TradingView chart.
- Don't build a control the system already has; pages only compose components from `src/ds` (see ARCHITECTURE).
