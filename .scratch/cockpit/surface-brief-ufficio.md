---
version: 1
slug: "frontend-src-pages-ufficio"
primary_target: "frontend/src/pages/ufficio"
related_targets: []
---

# Surface brief: Ufficio (/ufficio)

Mode: **Operate**. Build path: code-led. World: Legend (DESIGN.md), extended, not replaced. Source: `.scratch/cockpit/brief-ufficio.md` (confirmed by Luca 2026-11-22).

## Scope
Audience: Luca as the office's wildcard colleague, desktop and phone. Job: see who works on what, read every agent chat, watch tool calls live, intervene (say on a topic, enqueue_task on a ticker), see cost and tokens per agent. Constraints: every figure from the Runtime; missing backend contracts (agents, chat_topics, tool_calls, usage, SSE chat.message / tool.called / agent.status) sit behind typed adapters that say "non ancora esposto" instead of inventing data. No agent pause, no Bridge backend, no Evaluation.

## Direction contract
THESIS: the office as a live roster you can step into. Refuses the generic KPI dashboard: no hero metrics, no icon+title cards; each tile is a seat with a person, a task, their last words and a meter.
OWN-WORLD: Legend graphite tiles on the near-black desk, filled author avatars as the identity of each seat, status dots (working pulses softly only while live), segmented controls, concentric 12/8/6/4 radii, author colour only on that agent's marks.
STORY: Luca sees at a glance who is working and on which ticker, opens an agent, switches between its chats like Slack channels, reads the conversation signed message by message, watches tool calls arrive and expands one to read input and output, writes into the chat or assigns a task.
FIRST VIEWPORT: overview = page title "Ufficio" with a one-line office summary (working/waiting/idle, today cost and tokens) and Assegna task on the right; a grid of seat tiles, one per agent as the brief asks (avatar 36 px, name + role, status, current task with ticker tag, the agent's last line, last activity / cost / tokens today), a Costi e token tile below with period segmented control, and a 340 px Conversazioni recenti tile on the right. Agent view = three tiles: left side bar (agent switcher + that agent's chats), centre conversation with header (agent / chat, usage, Assegna task) and composer docked at bottom (primary action Invia), right tool-call stream with expandable blocks. Phone: overview as a list; agent view as chat selector + Chat/Tool segmented tabs.
FORM: three-zone workspace (Slack/Claude app); seed: none (pinned) — "Struttura (scelta di Luca: panoramica + chat)". Signature interaction: a tool block expands in place to input/output with duration and outcome; motion grammar: Legend tile-enter, 150 ms state colour, block expansion height ease-settle 220 ms.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved
Backend contract shapes are frontend-proposed until `backend-ufficio` lands.
