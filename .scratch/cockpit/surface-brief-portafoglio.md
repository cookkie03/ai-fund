---
version: 1
slug: "frontend-src-pages-portafoglio"
primary_target: "frontend/src/pages/portafoglio"
related_targets: []
---

# Surface brief: Portafoglio (`/portafoglio`)

Mode: **Operate**. Build: code-led, inside the established Legend world (DESIGN.md). Brief confirmed by Luca on 2026-11-22 (`.scratch/cockpit/brief-portafoglio.md`); JSON contract fixed in `.scratch/cockpit/handoff-backend-portafoglio.md`.

## Audience and job
Luca, owner of the account, managing the portfolio the agents trade, from desktop (most) and phone. Job: know in one look how the account is doing and where the risk sits, then act with the same rules as the agents: approve or reject orders, close or reduce, move stop and target with a dry-run preview, ask PM or Risk Analyst on the ticker topic, edit the Risk Gate limits with confirmation, reason and history.

## Constraints
Every number from the Runtime; missing reads say which endpoint they wait for; dev fixtures only behind `COCKPIT_PORTFOLIO_FIXTURES=1` on the Vite dev server. Capital actions disabled in Halt or when the Runtime is unreachable, with the reason. Phone 390 px: compact overview, tabs as a selector, positions as a list with a detail sheet.

## Direction contract
THESIS: the account read like a manager's statement, not a banking feed: one equity figure leads, and every figure below it is tied to the limit it must respect. Refuses the consumer-app stack of oversized cards and a lone line chart; refuses the pie chart.
OWN-WORLD: Legend unchanged: near-black desk, graphite tiles at 10 px, 12/8/6/4 concentric radii, Inter tabular figures, up/down only for P&L and direction, warn for "vicino al limite", down for "oltre", azure only for the one committing action. Limits drawn as a thin tick on sunken 6 px bars.
STORY: Luca sees equity, today and the curve against SPY; scans allocation against the 30% sector line; opens Posizioni to see open risk to the stop per row; acts from the row; checks Performance and attribution by agent; tightens or loosens a limit with a reason and sees the history.
FIRST VIEWPORT: desktop 1440: page header row (title, freshness, halt state); a summary band tile with equity at 30 px (the page's one large figure), day change tag, then a row of 7 small KPI meters; below it, the equity curve tile (left, ~62%) with period segmented control, SPY toggle and drawdown pane, beside the allocation tile (right) with sector bars and position bars with threshold ticks; the tabs tile starts at the fold with Posizioni visible. Primary action: per-row actions in Posizioni; Approva in Operazioni.
FORM: overview + tabs (pinned by Luca's brief). seed: none (pinned) — "Struttura: panoramica in alto + schede Posizioni, Operazioni, Performance, Rischio e vincoli".
Signature interaction: the threshold tick — every bar of exposure carries its limit, and the limit's state (entro, vicino, oltre) is the same word and colour in allocation, positions and Rischio e vincoli; editing a limit shows the new tick against current usage before confirming.
Motion grammar: Legend's: tiles settle in, tab content fades 4 px, bars grow once on first data, dialogs scale from 0.98; reduced motion collapses all.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved
`dry_run` response field names proposed to the backend session (see wiki notes). Sector data and agent attribution depend on the backend.
