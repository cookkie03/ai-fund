---
name: Trading Agent Cockpit
description: One desk shared by Luca and six trading agents, where every mark is signed.
colors:
  ground: "oklch(0.172 0.009 255)"
  panel: "oklch(0.152 0.009 255)"
  raised: "oklch(0.212 0.011 255)"
  hover: "oklch(0.235 0.012 255)"
  selected: "oklch(0.26 0.03 252)"
  line: "oklch(0.262 0.011 255)"
  line-strong: "oklch(0.33 0.012 255)"
  fg: "oklch(0.94 0.004 255)"
  fg-muted: "oklch(0.74 0.012 255)"
  fg-subtle: "oklch(0.64 0.013 255)"
  fg-faint: "oklch(0.5 0.012 255)"
  accent: "oklch(0.7 0.15 251)"
  accent-strong: "oklch(0.62 0.17 252)"
  up: "oklch(0.74 0.135 168)"
  down: "oklch(0.67 0.195 20)"
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
typography:
  title:
    fontFamily: "Inter Variable, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: "1.35rem"
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
  sm: "4px"
  md: "6px"
  lg: "8px"
spacing:
  hairline: "1px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
components:
  button-primary:
    backgroundColor: "{colors.accent-strong}"
    textColor: "{colors.fg}"
    rounded: "{rounded.md}"
    height: "32px"
    padding: "0 12px"
  button-primary-sm:
    backgroundColor: "{colors.accent-strong}"
    textColor: "{colors.fg}"
    rounded: "{rounded.md}"
    height: "24px"
    padding: "0 10px"
  button-ghost:
    textColor: "{colors.fg-muted}"
    rounded: "{rounded.md}"
    height: "28px"
    padding: "0 8px"
  button-ghost-hover:
    backgroundColor: "{colors.hover}"
    textColor: "{colors.fg}"
  tool-button-active:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.accent}"
    rounded: "{rounded.md}"
    size: "28px"
  author-chip:
    textColor: "{colors.author-technical}"
    rounded: "{rounded.sm}"
    height: "16px"
    typography: "{typography.label}"
  list-row-selected:
    backgroundColor: "{colors.selected}"
  popover:
    backgroundColor: "{colors.raised}"
    rounded: "{rounded.lg}"
---

# Design System: Trading Agent Cockpit

## Overview

**Creative North Star: "The Signed Desk"**

The cockpit is a professional trading terminal for one human who supervises autonomous agents. It follows the category standard (TradingView, IBKR TWS for the market surfaces; Claude, Linear, Slack for conversation) executed with full craft, and adds one idea the category lacks: every mark on the desk carries its author. Chart lines, watchlist rows, orders, analyses and messages are signed by Luca or by one of the agents, with a colour and a two-letter monogram that are the same everywhere.

The look is cool graphite, dense and quiet, built for long sessions under screen light. Colour is spent on meaning only: market direction, the one accent for selection and primary action, warnings, Halt, and authorship. No metaphors, no decorative surfaces; brand lives in precision of numbers, alignment and state.

**Key Characteristics:**
- Two-step graphite surfaces (panels a step darker than the work area) divided by 1 px hairlines, never cards.
- One azure accent for selection and primary action; teal-green and red only for market direction and order side.
- Authors own colours, shown as monogram chips, and the chart can show, hide and highlight marks per author.
- Inter with tabular numerals, 11 to 14 px dense scale.
- Motion only for state: 150 to 200 ms, price cells flash once, the status dot pulses only while the stream reconnects.
- Freshness is always visible: Live, Connessione, Dati vecchi with age, Runtime irraggiungibile.

## Colors

### Primary
- **Azure** (`accent`, `accent-strong`): selection, focus ring, active tab underline, active tool, primary buttons (Approva). Never used for market direction.

### Neutral
- **Graphite ground** (`ground`): the work area: chart, tables, dock.
- **Graphite panel** (`panel`): rail, watchlist, activity panel, top bar: one step darker than the work area.
- **Raised** (`raised`): popovers, menus, dialogs, inputs.
- **Hover / Selected** (`hover`, `selected`): row and control states; selected carries a trace of the accent hue.
- **Lines** (`line`, `line-strong`): hairline dividers; strong for input borders and chip outlines.
- **Text ramp** (`fg`, `fg-muted`, `fg-subtle`, `fg-faint`): primary text, secondary text, labels and metadata, decoration only.

### Semantic
- **Up / Down** (`up`, `down`): price change, P&L, buy/sell side, take profit and stop loss lines.
- **Warn** (`warn`): stale data, pending approval, low R:R, Halt preview copy.
- **Halt** (`halt`, `halt-ground`): the top bar and banner while trading is halted.

### Authors
- **Luca** amber, **Portfolio Manager** violet, **Tecnico** cyan, **Mercato** lime, **Sentiment** pink, **Fondamentali** sand, **Rischio** indigo, **Sistema** grey. Each author colour appears only on that author's marks: monogram chip, chart drawings and their labels.

### Named Rules
**The Meaning-Only Rule.** Every saturated pixel means something: direction, selection, warning, Halt or author. A colour that only decorates is removed.

**The Faint Rule.** `fg-faint` (3.2:1 on ground) is for separators and decoration, never for text a person must read. Readable metadata uses `fg-subtle` (5.7:1) or stronger.

## Typography

**Font:** Inter Variable (self-hosted via @fontsource-variable/inter), system sans fallback.

### Hierarchy
- **Title** (600, 14 px / 1.35rem): panel and dialog titles, symbol in the chart toolbar.
- **Body** (400, 13 px / 1.2rem): analyses, messages, decisions.
- **Data** (400, 12 px / 1.05rem, tabular numerals): table cells, prices, quantities, timestamps.
- **Label** (400, 11 px / 1rem): column headers, metadata, chips, legends.

### Named Rules
**The Tabular Rule.** Every number that can change or be compared uses `tnum` (`.num`), right-aligned in tables. Formats are Italian (`1.234,56`, `−2,07%`) with grouping always on; money is `$` prefixed.

## Layout

Desktop (1440 x 900): 52 px icon rail, 44 px top bar, then the page. The Terminale is watchlist 272 px, chart filling the centre with a 40 px toolbar, a 304 px tabbed activity panel (Agenti, Disegni) that can close, and a 232 px orders dock under chart and panel. The Bridge (340 px) docks on the right from 1280 px and opens as a sheet below that; it starts open from 1600 px.

Tablet (768 to 1279 px): the activity panel becomes a right sheet opened from the chart toolbar. Phone (under 768 px): compact top bar, chart at 56 vh, an approval strip when orders wait, then tabs (Watchlist, Attività, Ordini) and a bottom nav for the six pages.

Spacing is a 4 px grid: 4 within groups, 8 to 12 between items, 16 around panel content. Density is high by design; rows are 32 px in tables and 80 px in the watchlist (price, change, sparkline, author and note).

## Elevation & Depth

Flat and tonal. Depth comes from the two surface steps and hairlines, not shadows. Only floating layers (popover, menu, dialog, sheet, toast) sit on `raised` with a soft shadow so they separate from the desk. When the Runtime is unreachable the page content is desaturated and dimmed, which is the one depth effect tied to state.

## Shapes

Radius 6 px for controls and chips' containers, 4 px for monogram chips, 8 px for popovers and dialogs. Rectangles with hairline borders; no pills except status dots. Chart drawings keep the library's geometric forms.

## Components

### Buttons
Primary (azure, 32 px, 24 px in table rows) is reserved for the one action that commits: Approva, Approva e invia, Invia. Ghost buttons carry everything else; destructive actions (Halt, Rifiuta conferma) use the down colour. Disabled is 50% opacity and keeps a tooltip that names why (Halt attivo, Runtime irraggiungibile).

### Chips
**Author chip:** monogram in the author colour on a 17% tint with a 30% inset outline, optional short name, tooltip with full name and channel. **Status badge:** text on the semantic soft tint (Da approvare warn, Eseguito up, Rifiutato down, Annullato neutral).

### Navigation
Icon rail with tooltips; the active page uses `selected`. Panel tabs are text with a 2 px azure underline and an optional count.

### Tables
Header in label size and `fg-subtle`, hairline row dividers, numbers right-aligned and tabular, the selected ticker's rows tinted `selected`. Clicking a row selects its ticker on the chart.

### Author Layers (signature)
A legend on the chart lists every author with drawings on the current ticker and the count. Click hides or shows that author's marks; hover highlights them and dims the rest. Agents' drawings are locked; Luca's are editable and saved to the Runtime as annotations the agents read.

## Do's and Don'ts

### Do:
- **Do** sign every mark: drawings, watchlist rows, orders and messages show their author chip.
- **Do** show freshness and the account at all times, and say how old stale data is.
- **Do** keep primary azure for the one committing action in view.
- **Do** disable commands while the Runtime is unreachable or Halt is active, and say why.
- **Do** let the Runtime be the source of truth: show its refusal reasons verbatim inside the dialog that caused them.

### Don't:
- **Don't** use cards, gradients, glass or decorative shadows on the desk.
- **Don't** use green or red for anything but direction, side and P&L.
- **Don't** use `fg-faint` for readable text.
- **Don't** animate for entrance or delight; motion only marks a state change.
- **Don't** show sample or invented figures in production: every number comes from the Runtime.
