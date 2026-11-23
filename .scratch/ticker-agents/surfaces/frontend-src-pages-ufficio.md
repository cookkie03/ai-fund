---
version: 1
slug: "frontend-src-pages-ufficio"
primary_target: "frontend/src/pages/ufficio"
related_targets: ["frontend/src/features/office"]
---

# Surface brief: Ufficio (/ufficio)

Mode: **Operate**. Build path: code-led. World: Legend (DESIGN.md), extended, not replaced. Sources: `.scratch/cockpit/brief-ufficio.md` (2026-11-22) and `.scratch/ticker-agents/brief.md` (two-level office, 2026-11-22). Composition chosen by Luca 2026-11-22: "squadra, desk, proposte, facendo sì che si intuisca dalla UI (inconsapevolmente) la struttura del grafo degli agenti sul backend".

## Scope
Audience: Luca as the office's wildcard colleague, desktop and phone. Job: see who works on what across two levels (core team: PM + specialists; desk of per-ticker agents, 3 to 40), see proposals waiting for the PM and decide in its place (`decide_proposal`, `confirm:true`), read every chat, watch tool calls, write, assign tasks, see cost and tokens. Keep everything that works today. Contract field names from `.scratch/ticker-agents/handoff-backend.md` verbatim; missing reads say which endpoint they wait for.

## Direction contract
THESIS: the office as an org you can read without a chart. The hierarchy PM → ticker agents → specialists is carried by placement, reading order and shared marks (ticker tags, avatars), never by a drawn graph. Refuses the KPI dashboard and the node-and-edge diagram.
OWN-WORLD: Legend graphite tiles, filled author avatars (porcelain for ticker agents, author colours for the core team), status dots, segmented filters, 12/8/6/4 radii, colour only for meaning.
STORY: Luca reads left to right: the PM with its queue of proposals, the desk of ticker agents reporting to it, the specialists they call on. Hovering a ticker row lights the specialists working on that ticker; hovering a specialist lights its tickers. He decides a proposal, opens a ticker agent (chat, tools, strong link to the dossier) or the PM (chat, tools, proposal queue).
FIRST VIEWPORT: desktop 1440: title + one-line summary + Assegna task. Three columns: left 340 px the PM seat with "In attesa del PM" under it (ticker, direction, conviction, sizing, R:R, waiting time, Decidi); centre the Desk dei ticker tile (filters Tutti / In analisi / In attesa del PM / In portafoglio / Inattivi, dense 40 px rows); right 300 px the specialists as seats stacked, then Conversazioni recenti. Costi e token under the desk. Phone: PM + proposals, desk list with scrolling filters, specialists, recent, usage.
FORM: three-column reading order of the agent graph; seed: none (pinned) — "squadra, desk, proposte". Signature interaction: cross-highlight between ticker rows and specialists (dims the rest, as the chart's author layers). Motion: tile-enter, 150 ms state colour, `.agent-working` breathing, `.expand` disclosures.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved
Ticker-agent reads (`kind`, `ticker`, `supervisor` on agents; `proposals`; `dossiers`) land with `ticker-agents-backend`.
