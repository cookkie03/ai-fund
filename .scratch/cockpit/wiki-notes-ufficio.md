# Ufficio frontend: note per wiki e contratto backend

Branch `claude/ufficio-frontend-377c18`. Pagine `/ufficio` (panoramica) e `/ufficio/:agent` (vista agente).
Codice: `frontend/src/features/office/` (tipi, adapter, hook) e `frontend/src/pages/ufficio/` (UI).

## Cosa fa
- Panoramica: una tile "posto" per agente (avatar, ruolo, stato, lavoro corrente/ticker, ultima riga, ultima attività,
  costo e token di oggi), tile Costi e token (Oggi/7 giorni/30 giorni), Conversazioni recenti. Mobile 390: lista.
- Vista agente: agenti e chat dell'agente a sinistra, conversazione + composer al centro (`say`), chiamate ai tool dal
  vivo ed espandibili a destra. Assegna task (`enqueue_task`) e uso dell'agente nell'header. Mobile: selettore chat,
  tab Chat/Tool. Ctrl/⌘B e Ctrl/⌘Alt+B nascondono i pannelli laterali (layout condiviso con il Terminale).
- Niente pausa agenti, niente Bridge backend, niente Evaluation.

## Fonti oneste (`Sourced<T>`)
Ogni lettura è `runtime` (l'endpoint risponde), `derived` (ricostruita da letture reali + nota visibile) o
`unavailable` (stato vuoto che nomina l'endpoint atteso). Un 404 "Read endpoint 'x' not found" attiva il fallback.
Nessun dato finto in produzione: le fixture di sviluppo (`frontend/dev/office-fixtures.ts`) si attivano solo con
`COCKPIT_OFFICE_FIXTURES=1` su `vite` serve e non entrano nella build (verificato su dist).

| Lettura | Oggi senza backend-ufficio | Con il contratto |
|---|---|---|
| `GET /v1/read/agents` | derived dai cicli recenti (stato, modello, costi = null, nascosti) | runtime |
| `GET /v1/read/chat_topics?agent=` | derived: sonda `cockpit` + ticker di cicli e watchlist via `/v1/read/chat` | runtime |
| `GET /v1/read/tool_calls?agent=&cycle=&after=&limit=` | unavailable | runtime |
| `GET /v1/read/usage?agent=&from=&to=` | unavailable (Costi n/d) | runtime |
| SSE `chat.message`, `tool.started`, `tool.called`, `agent.status` | registrati, invalidano le query office; finché non arrivano si aggiorna con refetch 30 s e `message.appended`/`cycle.*`/`task.*` | dal vivo |

## Forme proposte (frontend → backend)
Vedi `frontend/src/features/office/types.ts`; i normalizzatori in `api.ts` accettano anche varianti (`params_json`,
`params_compacted`, ...).
- `agents[]`: `{name, role|null, model|null, status: "working"|"waiting"|"idle"|null, current: {kind, id, ticker, label}|null, last_activity_ts, today: {tokens_in, tokens_out, cost, calls}|null}`
- `chat_topics[]`: `{chat_id, agent, topic, title, ticker, cycle_id, last_message: {author, text, ts}|null, message_count}`;
  `topic` è la chiave che prendono `say` e `/v1/read/chat` (topic `cockpit` = chat di Luca con l'agente).
- `tool_calls[]`: `{id, ts, agent, chat_id, topic, cycle_id, tool, params, result, status: "running"|"ok"|"error", error, duration_ms, compacted: {params, result, at}}`
- `usage[]`: `{agent, tokens_in, tokens_out, cost, calls}` per periodo `from`/`to` (ISO; il frontend manda la mezzanotte locale per "oggi").
- Eventi SSE: `tool.started`/`tool.called` con almeno `{agent, id}`; `agent.status` con `{agent, status}`; `chat.message` con `{agent, topic}`.

## Da segnalare al backend
- La tabella `tool_calls` non ha `status` né `duration_ms`: senza, il frontend non può mostrare "in corso" né la durata.
- Serve il flag `compacted` quando la retention svuota params/result, altrimenti il blocco sembra vuoto per errore.
- Bug: `/v1/read/chat` fa `ORDER BY id ASC LIMIT n`, quindi restituisce i messaggi **più vecchi**; per una chat
  serve `ORDER BY id DESC LIMIT n` poi invertire (il frontend chiede 500 per ora).
- La lista cicli non include i messaggi (solo il dettaglio): la panoramica ne legge pochi per costruire l'attività recente.
- SSE `/v1/events` del Runtime sintetico non manda heartbeat: lo shell resta su "Connessione…" finché non arriva un
  evento (anche nella barra in alto, non solo nell'Ufficio). Da verificare lato Runtime.

## Verifiche
- `say` end-to-end su technical_analyst/cockpit: il messaggio appare nella chat. `enqueue_task`: task creato (AMD).
- Typecheck e build verdi; detector Impeccable `[]`; catture desktop 1440 e mobile 390 in `.impeccable/review/` (non tracciate).
- Review, critique e audit eseguiti in un solo contesto (subagenti Sonnet/Haiku non disponibili): `.scratch/cockpit/review-ufficio.md`.

## Avvio in locale
Runtime sintetico `uv run python scripts/dev_cockpit_server.py --port 8767 --db data/dev-cockpit-ufficio-fe.db`,
Vite `COCKPIT_PORT=5175 COCKPIT_RUNTIME_URL=http://127.0.0.1:8767 npx vite` (dati reali), con
`COCKPIT_OFFICE_FIXTURES=1 COCKPIT_PORT=5176` per vedere tutti gli stati.

---

# Note per il Wiki: Backend dell'Ufficio

Sintesi delle modifiche introdotte per l'Ufficio del cockpit (branch `worktree-backend-ufficio`):

## 1. Nuovi endpoint Read Model (`/v1/read`)
- `/v1/read/agents`: panoramica agenti configurati (`config/office.toml` e tabella `agents` in `OfficeDB`), con stato (`working`, `waiting`, `idle`), `current_task` (ticker e id ciclo/task), `last_activity_ts`, `today_tokens_in`, `today_tokens_out`, `today_tokens`, e `today_cost` calcolati da `llm_calls` per la giornata UTC corrente.
- `/v1/read/chat_topics?agent=`: elenco dei topic/canali dell'agente con `id` (chat_id), `topic`, `title`, eventuale `ticker` e `cycle_id`, `message_count`, `last_activity_ts`, e anteprima dell'ultimo messaggio.
- `/v1/read/tool_calls?agent=&cycle=&after=&limit=`: cronologia e stream delle invocazioni tool, con parametri, risultato, durata in ms, `success` (bool), eventuale `error`, `topic`, `cycle_id`, e flag esplicito `compacted: bool` (true se compattato dalla retention).
- `/v1/read/usage?agent=&from=&to=`: aggregazione delle chiamate LLM (`llm_calls`) per agente e periodo (timestamp ISO UTC), con token in/out, costo e conteggio chiamate.

## 2. Eventi Live SSE (`events` table)
Rispettato il modello single-writer: gli eventi nascono nella stessa transazione di scrittura del DB e vengono pubblicati sul bus in memoria su commit:
- `chat.message`: emesso su `OfficeDB.append_message` (da `say`, cicli o interazioni agenti) con dettagli completi (agente, topic, autore, testo, kind, ciclo, ts).
- `tool.called`: emesso su `OfficeDB.log_tool_call` (da `AgentEnvironment` o writer) con esito, durata e ciclo.
- `agent.status`: emesso su `OfficeDB.set_agent_status` con stato e task corrente.

## 3. Scenario di Sviluppo
- `scripts/dev_cockpit_scenario.py`: arricchito con agenti in stati differenti, chat multiple (incluse conversazioni con Luca e chat tematiche macro/semiconduttori), tool calls riuscite, fallite e compattate, storico chiamate LLM.
- `scripts/dev_cockpit_server.py`: aggiunto simulatore in background (`_live_event_simulator`) che emette periodicamente eventi SSE per mostrare lo stream animato in fase di sviluppo frontend.
