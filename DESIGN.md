---
name: Trading Agent Cockpit
description: One desk shared by Luca and six trading agents, where every mark is signed.
colors:
  desk: "oklch(0.1 0.004 260)"
  ground: "oklch(0.19 0.007 260)"
  raised: "oklch(0.235 0.009 260)"
  hover: "oklch(0.225 0.008 260)"
  selected: "oklch(0.25 0.014 258)"
  line: "oklch(0.255 0.008 260)"
  line-strong: "oklch(0.33 0.01 260)"
  fg: "oklch(0.94 0.004 255)"
  fg-muted: "oklch(0.74 0.012 255)"
  fg-subtle: "oklch(0.64 0.013 255)"
  fg-faint: "oklch(0.5 0.012 255)"
  accent: "oklch(0.7 0.15 251)"
  accent-strong: "oklch(0.62 0.17 252)"
  up: "oklch(0.8 0.17 152)"
  down: "oklch(0.7 0.19 25)"
  warn: "oklch(0.82 0.14 78)"
  halt: "oklch(0.58 0.2 25)"
  halt-ground: "oklch(0.24 0.06 22)"
  author-luca: "oklch(0.82 0.135 72)"
  author-pm: "oklch(0.74 0.13 302)"
  author-technical: "oklch(0.78 0.11 206)"
  author-market: "oklch(0.8 0.13 138)"
  author-sentiment: "oklch(0.76 0.13 352)"
  author-fundamental: "oklch(0.8 0.075 58)"
  author-risk: "oklch(0.74 0.1 276)"
  author-system: "oklch(0.7 0.01 255)"
  author-ticker: "oklch(0.87 0.022 240)"
typography:
  price:
    fontFamily: "Inter Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: "1.25"
    letterSpacing: "-0.025em"
    fontFeature: "\"tnum\" 1"
  title:
    fontFamily: "Inter Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: "1rem"
    letterSpacing: "-0.005em"
  body:
    fontFamily: "Inter Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: "1.2rem"
  data:
    fontFamily: "Inter Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: "1.05rem"
    fontFeature: "\"tnum\" 1"
  label:
    fontFamily: "Inter Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 400
    lineHeight: "1rem"
rounded:
  tag: "4px"
  item: "6px"
  control: "8px"
  tile: "12px"
  full: "9999px"
spacing:
  hairline: "1px"
  inset-control: "2px"
  xs: "4px"
  inset-tile: "6px"
  sm: "8px"
  gap: "10px"
  md: "12px"
  lg: "16px"
components:
  tile:
    backgroundColor: "{colors.ground}"
    rounded: "{rounded.tile}"
  button-primary:
    backgroundColor: "{colors.accent-strong}"
    textColor: "{colors.fg}"
    rounded: "{rounded.control}"
    height: "32px"
    padding: "0 12px"
  button-primary-sm:
    backgroundColor: "{colors.accent-strong}"
    textColor: "{colors.fg}"
    rounded: "{rounded.item}"
    height: "24px"
    padding: "0 10px"
  button-ghost:
    textColor: "{colors.fg-muted}"
    rounded: "{rounded.control}"
    height: "28px"
    padding: "0 8px"
  icon-button:
    textColor: "{colors.fg-subtle}"
    rounded: "{rounded.item}"
    size: "28px"
  segmented:
    backgroundColor: "oklch(0 0 0 / 0.3)"
    rounded: "{rounded.control}"
    padding: "2px"
  segmented-item-active:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.fg}"
    rounded: "{rounded.item}"
    height: "24px"
  author-avatar:
    backgroundColor: "{colors.author-technical}"
    textColor: "{colors.desk}"
    rounded: "{rounded.full}"
    size: "20px"
  badge:
    rounded: "{rounded.tag}"
    height: "20px"
    typography: "{typography.label}"
  list-row-selected:
    backgroundColor: "{colors.selected}"
    rounded: "{rounded.item}"
  popover:
    backgroundColor: "{colors.raised}"
    rounded: "{rounded.tile}"
    padding: "6px"
---

# Design System: Trading Agent Cockpit

## Overview

**Creative North Star: "The Signed Desk", Legend edition**

The cockpit is a professional trading terminal for one human who supervises autonomous agents. It follows the category standard (Robinhood Legend and TradingView for the market surfaces, VS Code for the workspace, Linear and Raycast for the controls) executed with full craft, and adds one idea the category lacks: every mark on the desk carries its author. Chart lines, watchlist rows, orders, analyses and messages are signed by Luca or by one of the agents, with a colour and a two-letter monogram that are the same everywhere.

The page is a near-black desk carrying rounded graphite tiles: watchlist, chart, activity, orders, Bridge. The gaps between tiles are the only separators, and they double as resize handles. Every tile around the chart can be hidden and resized like VS Code's side bar, secondary side bar and panel. Colour is spent on meaning only: market direction, the one accent for selection and primary action, warnings, Halt, and authorship.

**Key Characteristics:**
- Near-black desk, graphite tiles separated by 10 px gaps; no hairlines between regions.
- One price per screen leads at 30 px; everything else stays 11 to 13 px.
- A four-step radius scale that nests concentrically (tile 12, control 8, item 6, tag 4).
- Authors are filled round avatars; the chart can show, hide and highlight marks per author.
- Motion marks state and arrival: tiles slide in when shown, controls press, price cells flash.
- Freshness is always visible: Live, Connessione, Dati vecchi with age, Runtime irraggiungibile.

## Colors

### Primary
- **Azure** (`accent`, `accent-strong`): focus ring, primary buttons (Approva), the resize line under the pointer. Never used for market direction.

### Neutral
- **Desk** (`desk`): the shell background: top bar, rail, gaps between tiles.
- **Ground** (`ground`): every tile: chart, watchlist, activity, orders, Bridge. The step from desk to ground is the main depth cue.
- **Raised** (`raised`): popovers, menus, dialogs, the active thumb of a segmented control.
- **Hover / Selected** (`hover`, `selected`): row and control states; selected carries a trace of the accent hue and a 1 px inner highlight.
- **Lines** (`line`, `line-strong`): rare hairlines inside a tile (between activity sections, dialog parts); strong for input borders.
- **Text ramp** (`fg`, `fg-muted`, `fg-subtle`, `fg-faint`): primary text, secondary text, labels and metadata, decoration only.

### Semantic
- **Up / Down** (`up`, `down`): price change, P&L, buy/sell side, take profit and stop loss lines. The day change sits on its soft tint as a tag.
- **Warn** (`warn`): stale data, pending approval, low R:R, the pending count on the hidden orders toggle.
- **Halt** (`halt`, `halt-ground`): the top bar and a banner tile while trading is halted.

### Authors
- **Luca** amber, **Portfolio Manager** violet, **Tecnico** cyan, **Mercato** lime, **Sentiment** pink, **Fondamentali** sand, **Rischio** indigo, **Sistema** grey. Each author colour appears only on that author's marks: avatar, chart drawings and their labels. **Agenti del ticker** (`ticker:<SYM>`) share one porcelain colour (`author-ticker`): they are many and alike, so the monogram is the ticker itself (full symbol on 36 px seats) and colour stays the core team's identity.

### Named Rules
**The Meaning-Only Rule.** Every saturated pixel means something: direction, selection, warning, Halt or author. A colour that only decorates is removed.

**The Faint Rule.** `fg-faint` is for separators and decoration, never for text a person must read. Readable metadata uses `fg-subtle` or stronger.

## Typography

**Font:** Inter Variable (self-hosted via @fontsource-variable/inter), system sans fallback.

### Hierarchy
- **Price** (600, 30 px, -0.025em, tabular): the selected instrument's last price in the chart header; 22 px on phones. One per screen.
- **Title** (600, 13 px, -0.005em): tile titles, the symbol above the price, dialog titles at 16 px.
- **Body** (400, 13 px / 1.2rem): analyses, messages, decisions.
- **Data** (400, 12 px / 1.05rem, tabular numerals): table cells, prices, quantities, timestamps.
- **Label** (400, 11 px / 1rem): column headers, metadata, legends, segmented items at 12 px medium.

### Named Rules
**The Tabular Rule.** Every number that can change or be compared uses `tnum` (`.num`), right-aligned in tables. Formats are Italian (`1.234,56`, `−2,07%`) with grouping always on; money is `$` prefixed.

**The One Price Rule.** Only the chart header's price is large. Watchlist prices, equity and table figures stay at data size so the eye lands on the instrument in focus.

## Layout

Desktop (1440 x 900): a 56 px icon rail and a 48 px top bar on the desk, then the workspace of tiles with 10 px gaps:
- **Side bar** (watchlist, 272 px, 220 to 420): left, full height.
- **Chart** (fills the centre): a 68 px header with symbol, price and day change, then timeframe, indicators and drawing tools as segmented groups.
- **Secondary side bar** (activity, 312 px, 264 to 460): right of the chart, tabs Agenti and Disegni.
- **Panel** (orders, 240 px, 132 to 520): under chart and activity.
- **Bridge** (340 px): a tile on the far right from 1280 px, a sheet below that; it starts open from 1600 px.

### Named Rules
**The VS Code Rule.** Every tile around the chart can be hidden and resized. Toggles live in the top bar (solid icon while the tile is shown, dashed while hidden) and as a close button in each tile header, with the VS Code shortcuts: Ctrl/⌘ B watchlist, Ctrl/⌘ Alt B activity, Ctrl/⌘ J orders. Dragging a gap resizes the tile next to it, arrow keys step 16 px (48 with Shift), double click restores the default. Sizes and visibility persist per browser (`cockpit.layout`). When the orders tile is hidden and orders wait for approval, the toggle carries a warn count. Below 1280 px the activity tile starts hidden unless a saved layout says otherwise.

Phone (under 768 px): compact top bar, chart at 56 vh, an approval strip when orders wait, then a segmented control (Watchlist, Attività, Ordini) over one tile, and a bottom nav for the six pages. Drawing tools are hidden on phones.

Spacing is a 4 px grid with two insets that drive the radius scale: 2 px inside a control, 6 px inside a tile. Rows are 32 px in tables and 80 px in the watchlist.

**Ufficio** (`/ufficio`, `/ufficio/:agent`): the agents' office.
- **Overview** (desktop): a grid of seat tiles (auto-fill, 296 px minimum), the Costi e token tile under it, and Conversazioni recenti as a 340 px tile on the right from 1024 px. On phones the seats become one list tile with cost on the right.
- **Agent view** (desktop, from 1024 px): side list (agents, then that agent's chats) left, conversation in the centre, tool calls right. It reuses the shell layout, so Ctrl/⌘ B and Ctrl/⌘ Alt B hide the two side tiles and the gaps resize them. On phones: back link and avatar, a chat selector menu, then Chat and Tool tabs over one tile.

## Elevation & Depth

Tonal. The desk-to-ground step separates tiles; there are no borders around them. Inside a tile, the active segmented thumb is `raised` with a 1 px drop shadow and a half-pixel top highlight, and primary buttons carry the same material highlight. Floating layers (popover, menu, dialog, sheet, toast) sit on `raised` with a hairline and a long soft shadow. When the Runtime is unreachable the page content is desaturated and dimmed, the one depth effect tied to state.

## Shapes

### Named Rules
**The Concentric Rule.** A shape nested inside another uses the outer radius minus the inset, so curves stay parallel:
- **Tile 12 px**: tiles, dialogs, sheets (outer edge), popovers and menus.
- **Control 8 px**: buttons, inputs, segmented controls, tab and tool groups, banners, the active rail item.
- **Item 6 px**: anything inset in a tile by 6 px or in a control by 2 px: list rows, table rows, menu items, segmented thumbs, tool buttons, icon buttons, tooltips, 24 px buttons.
- **Tag 4 px**: badges, counts, the day change, keyboard hints.
- **Full circle**: only author avatars and status dots. No other pills.

Radii are tokens (`rounded-tile`, `rounded-control`, `rounded-item`, `rounded-tag`); a raw `rounded-md` or pixel radius is a bug. Chart drawings keep the library's geometric forms.

## Motion

- Tiles slide 10 px and fade in over 260 ms on the settle curve (`cubic-bezier(0.32, 0.72, 0, 1)`) when shown; hiding is instant.
- Buttons and tool buttons scale to 0.94 to 0.97 while pressed; colours change over 150 ms.
- Price cells flash once on change; the status dot pulses only while the stream reconnects.
- Reduced motion collapses every animation and transition to 1 ms, except the price flash, which is a colour fade and carries information.
- A resize drag updates the layout at most once per frame.
- A working agent's status dot breathes in the agent's colour (`.agent-working`, 2.4 s). It is the only looping animation outside reconnects, and it stops when the agent is no longer working.
- Tool blocks and other disclosures open by animating grid rows from 0fr to 1fr over 220 ms on the settle curve (`.expand`); new rows fade up 4 px (`.row-arrive`).

## Components

### Tiles
Ground surface, 12 px radius, `overflow-hidden`. The header is 44 px, no divider: title at 13 px semibold, a count tag, actions on the right ending with the tile's hide button.

### Buttons
Primary (azure, 32 px, 24 px in table rows) is reserved for the one action that commits: Approva, Approva e invia, Invia. Ghost buttons carry everything else; destructive actions (Halt, Rifiuta conferma) use the down colour. Disabled is 50% opacity and keeps a tooltip that names why (Halt attivo, Runtime irraggiungibile). Icon buttons are 28 px with a tooltip that shows the shortcut in a tag.

### Segmented controls
A sunken track (black at 30%, 2 px inset, 8 px radius) with 24 px items at 6 px radius (32 px under a coarse pointer); the active item is `raised` with a material shadow. Used for timeframe, tile tabs, order scope, drawing tools and the phone tab bar.

### Chips
**Author avatar:** a filled circle (20 px, 18 px in dense rows) in the author colour with the monogram in desk-dark bold text, optional short name, tooltip with full name and channel. **Status badge:** text on the semantic soft tint (Da approvare warn, Eseguito up, Rifiutato down, Annullato neutral), 4 px radius.

### Navigation
Icon rail on the desk with tooltips; the active page is a ground-coloured 8 px square, like a tile seen from the side.

### Tables
Header in label size and `fg-subtle` on the tile surface, no row rules: rows are inset 6 px and light up on hover as 6 px rounded bars; the selected ticker's rows are tinted `selected`. Numbers right-aligned and tabular. Clicking a row selects its ticker on the chart.

### Chart
No grid, solid 1 px crosshair, thin solid drawings with the author's monogram only (the text lives in the Disegni tab), order levels at half opacity, volume at 12%, dotted RSI 70/30 guides at 30%. The legend under the header carries OHLC and indicator values; the symbol is not repeated there.

### Author Layers (signature)
A legend on the chart lists every author with drawings on the current ticker and the count. Click hides or shows that author's marks; hover highlights them and dims the rest. Agents' drawings are locked; Luca's are editable and saved to the Runtime as annotations the agents read.

### Seat tile (Ufficio)
One tile per agent, all of it a link to the agent's view. A 36 px avatar, name and role; the status mark top right; a work line (ticker tag plus what it is doing); the agent's last line in quotes with its ticker; then three meters (Ultima attività, Costo oggi, Token oggi). Assegna task appears on hover or focus. A field the Runtime does not send is left out, never shown as zero.

### Status mark
A 8 px dot and a word. Al lavoro: filled in the author's colour and breathing. In attesa: warn. Inattivo: hollow ring in `fg-subtle`. Compact form (dot only, tooltip) in dense rows. If the Runtime sends no state, nothing is drawn.

### Side list (Ufficio)
Slack's sidebar inside a tile: Agenti as 32 px rows (avatar, name, current ticker, compact status), then Chat di X as two-line rows (topic icon, title, count tag, time; author short name and last line). `#` marks a ticker chat, a speech bubble marks Luca's own chat. Section breaks are spacing, not rules.

### Conversation and composer
Messages group by author within 5 minutes, with a centred day label (Oggi, Ieri) and the list anchored to the bottom like a chat. The composer is a raised control: textarea that grows to 6 lines, Invio sends and Maiusc Invio breaks, keyboard hints as tags, Invia as the one primary. A refusal from the Runtime shows verbatim above the field.

### Tool block
A row per tool call in the right tile, newest first with running calls on top: check, spinner or warn icon, tool name in mono, a one-line summary of the parameters (or the error, in warn), duration and time. It opens in place (`.expand`) to show the chat and cycle, Input and Output as mono JSON with Copia, and a note when retention compacted the payload. The tile header says Dal vivo, Fermo da X or Connessione… and filters Tutte or Errori.

### Usage
Costi e token tile: a period control (Oggi, 7 giorni, 30 giorni), rows with the agent, a share bar in the author colour, calls, tokens in and out, cost, and a total. In the agent view the same data sits behind a ghost trigger (cost and tokens today) that opens a popover. When the Runtime does not expose usage, the control is disabled and the trigger reads Costi n/d.

### Avatars
Author avatars have two more sizes for the office: 28 px (`md`, messages) and 36 px (`lg`, seats).

### Ticker desk (Ufficio)
The office reads left to right as the agent graph: the PM seat with its **In attesa del PM** queue, then the **Desk dei ticker** (one 40 px row per ticker agent, "riporta a PM" from `supervisor`), then the specialists they call on. Rows carry the porcelain avatar, ticker, direction tag, conviction, stale count (history icon + number, warn), state word, proposal tag and age; specialist avatars and cost appear only when the tile is wide enough (container queries). Filters as a segmented control with counts (Tutti, In analisi, In attesa del PM, In portafoglio, Inattivi), a filter field above 10 rows. Hovering a ticker row lights the specialists working on it and the reverse. Ticker agents fold into one expandable row in Costi e token and into a collapsible section of the side list.

### Proposal queue
Oldest first: ticker agent avatar, ticker (link to its dossier), direction, "da X" waiting time, conviction, sizing and R:R (warn under 1,5), and a ghost **Decidi**. In the PM's agent view the same queue sits above the tool stream.

### Decide dialog
"Decidi al posto del PM": a summary strip (avatar, ticker, direction, conviction, sizing, R:R), a segmented Accetta / Rimanda / Rifiuta / Chiedi, a resize field for Accetta and a date for Rimanda, a required reason, and one primary labelled with the action. Sends `decide_proposal` with `confirm: true`; Halt disables Accetta and says why; refusals show verbatim in the dialog.

### Dossier (Scheda del ticker)
`/ticker/:symbol` is a mosaic of tiles. A full-width header: symbol over a 30 px price, name, sector and cap; Scheda status with version and who updated it; the ticker agent with its status mark; the position when invested (P&L in up/down); links to Grafico, Chat dell'agente, Portafoglio; a Halt line when halted; the **Firme** legend. Then Tesi (7 columns) beside **Proposta e Risk Gate** (5: a stop–entry–target ladder with the current price as an accent diamond, levels, the verdict and every guardrail, Decidi as the tile's primary), five specialist tiles (lead fact in body size, older facts smaller; stale facts recede in `fg-muted` with a warn "Vecchio · age" tag; superseded ones are struck through and folded behind "Mostra n fatti superati"), Storico decisioni beside Lezioni, Note di Luca (amber-tinted, signed, composer with Invio to sign) beside Versioni. Confidence and conviction are a number plus a 4 px track in the author's colour. On a phone the order is decision first (Proposta, Tesi, Analisi, Note, Decisioni, Lezioni, Versioni) under a sticky section index that marks the current section.

### Signature on the dossier
As on the chart: hovering an author's avatar, or a name in the Firme legend, lights every fact they signed across the mosaic and dims the rest to 30%; clicking a legend name pins it.

### Honest sources
Data the Runtime does not expose yet is either rebuilt from real reads (with a quiet info note that says how) or shown as unavailable with the endpoint it waits for. Never sample data.

## Do's and Don'ts

### Do:
- **Do** sign every mark: drawings, watchlist rows, orders and messages show their author avatar.
- **Do** show freshness and the account at all times, and say how old stale data is.
- **Do** keep primary azure for the one committing action in view.
- **Do** disable commands while the Runtime is unreachable or Halt is active, and say why.
- **Do** let every tile around the chart hide and resize, and remember the layout.
- **Do** let the Runtime be the source of truth: show its refusal reasons verbatim inside the dialog that caused them.

### Don't:
- **Don't** draw borders around tiles or hairlines between regions: the desk gap separates them.
- **Don't** use a radius outside the four tokens, or a pill for anything but avatars and dots.
- **Don't** use gradients, glass or decorative shadows.
- **Don't** use green or red for anything but direction, side and P&L.
- **Don't** use `fg-faint` for readable text.
- **Don't** show sample or invented figures in production: every number comes from the Runtime.
