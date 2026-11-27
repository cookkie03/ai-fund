# Decisions

Every decision the UI needs, settled with Luca. The only step left before building is in the Claude Design project on the codebase: **draw every page of §3 ex ante** (desktop + phone, light + dark) using only this system's components and blocks, then build the pages as compositions (ARCHITECTURE).

## 1. Foundations

| Topic | Decision |
| --- | --- |
| Library | Vanilla shadcn/ui on **Base UI** (`base-vega`). No Radix (cmdk's Command replaced by Combobox). Every shadcn Base UI component is in the system |
| Inspiration | ui.shadcn.com, pro.shadcn.co, shadcn.io; Revolut / Trade Republic: simple to navigate, professional underneath. No financial terminals |
| Language | English everywhere (glossary §6) |
| Theme | Light (default) + dark; switch in Luca's avatar menu |
| Grays | shadcn **neutral**, monochrome: no brand hue, `primary` near-black / near-white |
| Separation | Cards with a 1 px ring/border (shadcn classic) |
| Up / down | Sober green `success` / red `destructive`, always with sign or arrow |
| Attention | Amber `warning` |
| Text | Two grays: `foreground`, `muted-foreground` |
| Charts | Grayscale `chart-1…5`; **the TradingView chart is never restyled** |
| Author sign | One `AgentAvatar`: gray initials circle, Luca solid, agents muted, status dot |
| Font | Inter Variable |
| Radius | **14 px** (soft, banking-app) |
| Icons | Lucide |
| Density | shadcn defaults; compact 32 px rows and `Card size="sm"` for positions, orders, tool calls |
| Numbers | en-US: `$1,234.56`, `−2.07%`, tabular |
| Currency | Base USD in totals and tables; native currency too on an instrument's row and page |
| Time | Relative under 24 h, then `Nov 26, 14:32` |
| Motion | **Everything moves, gently**: reveal with stagger, count-up figures, bars grow, hover lift, price flash, breathing Working dot; reduced motion keeps only the flash |
| Mark | `AfMark`: "AF" in a primary rounded square (`af-mark.svg`, `af-mark-dark.svg`) |

## 2. Global shell

| Element | Decision | Block |
| --- | --- | --- |
| Frame | Sidebar **inset** variant, collapsible to icons | `AppShell`, `AppSidebar` |
| Navigation | Home · Portfolio · Approvals (count) · Agents · Markets · News · Assistant; Settings + avatar menu in the footer | `AppSidebar` |
| Landing page | **Home** | §3.1 |
| Sidebar header | `AfMark` + "AI Fund" + the account switcher showing the **account name Luca chose** (see §8 Accounts) | `AppSidebar` |
| Top bar | Trigger · breadcrumb · search (⌘K → Combobox) · freshness · Bridge · notifications · Halt | `TopBar` |
| Freshness | Dot + word + age, always visible | `FreshnessBadge` |
| Halt | Destructive button → AlertDialog; halted = destructive `Alert` under the top bar, Resume trading | `HaltButton`, `Alert` |
| Notifications | Popover with `Item` rows: approvals needed, orders filled, limits near/over, runtime state | `TopBar` |
| Toasts | Order filled, approval needed, data stale, runtime back | `Toaster` |
| Runtime unreachable | Freshness turns red, capital actions disabled with tooltip | `FreshnessBadge`, `Tooltip` |
| Bridge | Assistant page **and** the same chat in a right `Sheet` from the top bar | `ChatThread`, `Composer`, `Sheet` |
| Phone | Bottom tabs Home · Portfolio · Approvals · Agents · More; details in a bottom `Drawer` | `MobileTabBar`, `Drawer` |

## 3. Pages — what each one holds

Each page: one job, one hero, cards in order, detail on demand, one primary action.

### 3.1 Home
- Job: how is the fund doing, and what needs me now.
- Hero: `HeroBalance` (total equity, change today, period).
- Cards: `StatCard` × 3 (Unrealized P&L, Cash vs reserve, Open risk) · Needs your approval (top 3 `ProposalCard`, link to Approvals) · `EquityChart` · Agents at work (avatars with status) · `ActivityFeed` (5 rows).
- Phone: hero, insights `Carousel`, approvals, activity.

### 3.2 Portfolio
- Job: what we own and how it performs.
- Hero: `HeroBalance` + `StatCard`s (Invested %, Cash % + min, Positions n/max, Realized today).
- `Tabs`: **Overview** (`EquityChart` with SPY and drawdown, `AllocationList`) · **Positions** (`PositionsTable`; a row opens the instrument; actions in its menu → capital `Dialog` with dry-run preview and the risk gate's answer) · **Activity** (`OrdersTable`, trades, `Pagination`) · **Risk** (`LimitBar` per limit; Edit limits → two-step `Dialog`: values + reason → Review before → after → Confirm & apply; history).

### 3.3 Approvals
- Job: decide what agents propose.
- Hero: count waiting + oldest wait.
- Cards: `ProposalCard` grid, oldest first; Decide → `DecideDialog` (Accept · Postpone · Reject · Ask, size, date, required reason). `Empty` when nothing waits.

### 3.4 Markets
- Job: look at an instrument's price with the agents' marks.
- `MarketsWorkspace` (resizable): `Watchlist` | TradingView chart with `AuthorFilter` (show / hide each author's drawings) | Agents / Drawings tabs; Orders below. `Menubar` (View: panels; Chart: indicators). Sizes persist per browser.

### 3.5 Instrument (equities, bonds, companies)
- Job: everything we know and propose about one instrument.
- Header card: symbol, price (native + base), name, sector, the instrument agent with status, the position, links (Chart, Agent chat, Portfolio), Signatures filter.
- `Tabs`: **Overview** (thesis, proposal & risk gate with entry–stop–target and verdict, Decide) · **Analysis** (one card per specialist; stale facts with a warning badge; superseded facts in an `Accordion`) · **Notes** (Luca's notes + `Composer`) · **History** (decisions, lessons, versions).

### 3.6 Agents and Agent detail
- Job: who is working on what, and what it costs.
- Agents: `AgentTree` (PM → Risk Manager and instrument agents → specialists) beside an `AgentCard` grid; Costs & tokens card (period, per-agent share, total).
- Agent detail: header (`AgentAvatar` lg + status + meters) and `Tabs` **Chat** (`ChatThread`, `Composer`, `Marker` day labels) · **Tool calls** (`ToolCallRow` list, All / Errors filter, freshness) · **Costs**.

### 3.7 Assistant
- Job: talk to the Bridge, which can use the same commands as the UI.
- `ChatThread` + `Composer` full height; commands the Bridge runs show as `Trace` lines with inline confirmations (`AlertDialog` for capital actions).

### 3.8 News
- Job: read, filter and send news to agents.
- List of `Item`s (source, time, tickers as badges) beside a reader card; filters (`ToggleGroup`, `Combobox`, date `Calendar`); "Send to agent" in the reader.

### 3.9 Settings
- shadcn settings layout: left sub-nav + `Field` forms in cards. Sections: Agents, Models, Prompts, Schedules, Budgets, Providers, Account, Database, Runtime health.

## 4. Components

All shadcn Base UI components are in the system and used as they ship:

- **Actions:** Button, ButtonGroup, Toggle, ToggleGroup.
- **Forms:** Input, InputGroup, InputOTP, Textarea, Label, Field, Select, NativeSelect, Combobox, Checkbox, RadioGroup, Switch, Slider, Calendar.
- **Data display:** Card, Table, Badge, Item, Progress, Empty, Kbd, Skeleton, Spinner, Accordion, Collapsible, Chart, Carousel.
- **Navigation:** Sidebar, Tabs, Breadcrumb, Pagination, NavigationMenu, Menubar.
- **Overlays:** Dialog, AlertDialog, Sheet, Drawer, Popover, HoverCard, Tooltip, DropdownMenu, ContextMenu.
- **Feedback:** Alert, Toaster.
- **Chat:** Message, Bubble, Marker, Trace, CodeBlock, Attachment.
- **Layout:** Separator, ScrollArea, Resizable, AspectRatio.

Button use: `default` only for the one committing action (Approve, Send, Confirm & apply); `outline` for secondary (Decide, Details); `ghost` for Cancel and toolbar icons; `destructive` for Halt, Reject, Close position; `sm` inside cards and tables.

## 5. Blocks (all built, see the Blocks groups)

| Group | Blocks |
| --- | --- |
| Identity & motion | AgentAvatar, AfMark, Delta, StatusBadge, Motion (Reveal, AnimatedNumber, PriceFlash) |
| Shell | AppShell, AppSidebar, TopBar, FreshnessBadge, HaltButton, MobileTabBar |
| Pages | PageHeader, HeroBalance, StatCard |
| Portfolio | PositionsTable, OrdersTable, LimitBar (gray → amber → red + word), AllocationList, EquityChart |
| Approvals | ProposalCard, DecideDialog |
| Markets | MarketsWorkspace (resizable), Watchlist, TradingViewChart (untouched), AuthorFilter |
| Agents | AgentCard, AgentTree (expandable), ToolCallRow, ActivityFeed, ChatThread, Composer |

## 6. Glossary (Italian → English)

| Italian | English |
| --- | --- |
| Approva · Approva e invia · Invia | Approve · Approve & send · Send |
| Rimanda · Rifiuta · Decidi · Annulla | Postpone · Reject · Decide · Cancel |
| Accetta · Chiedi | Accept · Ask |
| Decidi al posto del PM | Decide for the Portfolio Manager |
| Ordini · Attività · Portafoglio · Ufficio · Terminale · Notizie · Configurazioni · Assistente | Orders · Activity · Portfolio · Agents · Markets · News · Settings · Assistant |
| Scheda del ticker | Instrument |
| Dati vecchi · Connessione… · Runtime irraggiungibile · Fermo da 2 min | Stale data · Connecting… · Runtime unreachable · Stopped for 2 min |
| Halt attivo | Trading halted |
| Da approvare · Eseguito · Rifiutato · Annullato | Pending approval · Filled · Rejected · Cancelled |
| Entro · Vicino · Oltre | Within limit · Near limit · Over limit |
| Al lavoro · In attesa · Inattivo | Working · Waiting · Idle |
| Firme · Disegni · Agenti | Signatures · Drawings · Agents |
| Costi e token · Costo oggi · Token oggi · Ultima attività | Costs & tokens · Cost today · Tokens today · Last activity |
| Oggi · 7 giorni · 30 giorni | Today · 7 days · 30 days |
| Conversazioni recenti · Assegna task | Recent conversations · Assign task |
| Desk dei ticker · In attesa del PM | Ticker desk · Waiting for PM |
| Tesi · Proposta e Risk Gate · Storico decisioni · Lezioni · Note di Luca · Versioni | Thesis · Proposal & risk gate · Decision history · Lessons · Luca's notes · Versions |
| Vecchio · Mostra n fatti superati | Stale · Show n superseded facts |
| Rivedi · Conferma e applica | Review · Confirm & apply |
| Storico troppo corto · Dati di esempio | Not enough history · Sample data |
| PnL non realizzato · Realizzato oggi · Investito · Cassa · Posizioni · Rischio aperto | Unrealized P&L · Realized today · Invested · Cash · Positions · Open risk |
| Tecnico · Mercato · Sentiment · Fondamentali · Rischio · Sistema · Subagente | Technical · Market · Sentiment · Fundamental · Risk · System · Subagent |

## 7. Next step

In the Claude Design project on the codebase: draw every page of §3 ex ante — desktop and phone, light and dark — from these blocks; then move the `ds/` folder into the frontend and build the pages as compositions.

## 8. Accounts (settled 2026-11-27)

- One account = one broker account. Creating it means choosing the broker (Alpaca, IBKR, …), the endpoint URL under Advanced (paper or live URL) and the credentials.
- **The software does not know or care whether an account is paper or live.** Backend and frontend carry no paper/live flag and never show "Live" or "Paper" as a system state. Luca names his accounts (e.g. "Alpaca · Paper") to tell them apart; the UI shows that name only.
- Consequence for the design system: `AppSidebar` drops `mode: "Live" | "Paper"`; its header shows the account switcher with the account name (Q10). "Live" in `FreshnessBadge` means live **data**, not a live account.

## 9. Page design log — Home (in progress, grilling with Luca)

| # | Decision |
| --- | --- |
| Q1 | `/` opens Home; Assistant moves to `/assistant` and stays in the Bridge Sheet |
| Q2 | Job: how the fund is doing. What needs Luca is the next section, not a second job |
| Q3/Q11 | Hero: **Total value** (positions at market value + cash, base USD, any instrument class), Popover on the label with the definition |
| Q4 | The 3 oldest proposals with Approve and Decide, plus "View all" to Approvals |
| Q5/Q16 | A small curve under the hero with a minimal built-in selector 1D · 1W · 1M (default 1D); the change under the figure follows the period. Full chart stays in Portfolio |
| Q6 | Hero + at most 3 sections; everything else behind a link, Sheet or Popover |
| Q7 | Desktop 1440 first, phone derived |
| Q8 | Sample figures with a "Sample data" badge in drawings only; real data after wiring |
| Q9 | Today's Briefing becomes the Home section "Needs you" (counts, items by severity, Ask the Bridge, Mark as read) and holds the 3 proposals; a compact Briefing stays as the opening of an empty Assistant chat |
| Q10 | Account switcher in the sidebar header; market clock beside freshness in the top bar; no equity figure in the top bar |
| Q13 | Oldest proposals first, same order as Approvals |
| Q15 | StatCards: Unrealized P&L, Cash vs reserve (LimitBar), Open risk (LimitBar + Within/Near/Over); positions n/max, realized today and invested stay in Portfolio |
| Q17 | Backend to add: aggregate `open_risk` in `portfolio_summary` and a unified activity route. No paper/live field (§8) |
| Q18 | A "Today" page in the design canvas (captures + inventory of each current page) **and** the local dev server on Luca's machine for real time |
