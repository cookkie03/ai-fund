---
version: 1
slug: "frontend-src-pages-ticker"
primary_target: "frontend/src/pages/ticker"
related_targets: ["frontend/src/features/dossier"]
---

# Surface brief: Scheda del ticker (/ticker/:symbol)

Mode: **Operate** (with Read passages). Build path: code-led. World: Legend (DESIGN.md), extended, not replaced. Source: `.scratch/ticker-agents/brief.md` (confirmed by Luca 2026-11-22), structure chosen by Luca on 2026-11-22: "Tessere a mosaico".

## Scope
Audience: Luca, and by reference every agent, desktop and 390 px phone. Job: read the always-current investment state of one ticker the way an analyst reads a research note: who thinks what, since when, how sure, and whether it still holds; then act (sign a note with `add_dossier_note`, decide the pending proposal with `decide_proposal` + `confirm:true`, jump to the chart, the ticker chat, the position). Constraints: every figure from `GET /v1/read/dossier`, `dossier_history`, `proposals`, `agents`; contract field names verbatim; unavailable states name the endpoint; dev fixtures only behind `COCKPIT_TICKER_FIXTURES`. The ticker proposes, the PM decides, the Risk Gate is sovereign.

## Direction contract
THESIS: a signed research dossier, not a profile page. Every fact wears author, date, confidence and status; age is visible as recession, never hidden. Refuses the stock-quote page (big chart, KPI strip) and the generic card grid of equal boxes.
OWN-WORLD: Legend graphite tiles on the near-black desk, 12/8/6/4 concentric radii, author avatars on every fact, the porcelain ticker-agent avatar, a confidence meter as a 4 px track in the author's colour, stale facts at reduced contrast with a "vecchio" tag, superseded struck through, Luca's notes in amber signature.
STORY: Luca opens NVDA, sees in one line the price, the dossier state, the ticker agent and its status; reads the thesis (direction, conviction, pro/contro, dated catalysts, next check), the proposal with every Risk Gate rule ticked or failed, then each specialist's latest view with older ones receding; scrolls decisions, lessons, versions; signs a note; decides if a proposal waits.
FIRST VIEWPORT: desktop 1440: header tile full width (symbol 13 px over price 30 px, name/sector, dossier status badge, version + updated by, agent chip with status, position block if invested, links Terminale / Chat del ticker / Portafoglio at right). Below, a 12-column mosaic: Tesi (7) beside Proposta e Risk Gate (5) with Decidi as the one primary when a proposal is pending; then the five specialist tiles in a row. Phone: compact header, sticky section index (segmented scroller), tiles stacked.
FORM: mosaic of tiles, item 1 of the dealt three; seed:c2408f59ce1eda27 — "Tessere a mosaico" chosen by Luca (structured-question channel). Signature interaction: hovering an author avatar in any tile highlights every fact by that author across the mosaic and dims the rest (author layers, as on the chart). Motion grammar: Legend tile-enter on first paint, 150 ms state colour, notes arrive with `.row-arrive`, disclosure via `.expand`.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved
Backend lands on `ticker-agents-backend`; `decide_proposal` payload field names beyond `confirm` are frontend-proposed (`proposal_id`, `action`, `reason`, `sizing_fraction`, `next_check_date`).
