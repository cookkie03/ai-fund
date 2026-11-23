# Note per l'aggiornamento della Wiki (Backend Assistente & Bridge Agent)

Annotazioni per la sessione principale da registrare nella wiki (`/home/luca/trading-agent-wiki/wiki/`):

## 1. Decision Log (`system/foundation/decision-log.md`)
- **Data**: 2026-11-23
- **Decisione**: **Assistente, Bridge Agent e Briefing nel Runtime unico**
- **Effetto**:
  - Il Bridge Agent entra nello scope del cockpit come agente autonomo reale (`bridge`, `kind: "core"`, `supervisor: null`) configurato in `config/office.toml` e `config/office_settings.py` con prompt in italiano (`prompts/bridge.md`).
  - Turni di ragionamento eseguiti nel worker asincrono del Runtime (`BridgeRunner`), serializzati per conversazione, protetti da budget di passi e budget giornaliero (`daily_budget`).
  - Accesso in lettura completo allo stato dell'ufficio (portafoglio, ordini, trade, limiti, schede/dossier, chat agenti, tool calls, eventi, briefing).
  - Comunicazione bidirezionale verso gli agenti via `message_agent {agent, topic, text}` con prefisso `[Per conto di Luca]`. Le risposte degli agenti rientrano nella conversazione come messaggi `kind: "agent_relay"` e avviano un turno di sintesi automatica. Messaggi al PM generano contestualmente uno Scheduled task.
  - Sovranità del Risk Gate e protezione del capitale: il Bridge non ha tool diretti per azioni con capitale; usa `propose_action` con anteprima (`dry_run`). L'esecuzione avviene solo tramite `bridge_action_decide` con conferma esplicita dell'utente (`confirm: true`), riusando lo stesso handler originario con attore `luca` e rieseguendo tutte le verifiche real-time.
  - Lettura deterministica del briefing (`/v1/read/briefing`) con variazioni di portafoglio, conteggi chiave, lista elementi delle 10 categorie (`trade`, `order_pending`, `proposal_pending`, `proposal_decided`, `alert`, `halt`, `resume`, `dossier`, `agent_error`, `risk_limits`) e sintesi `summary_text` scritta dal Bridge con cache.
  - Titolazione nitida automatica post-primo turno (`BridgeRunner`) e supporto per filtri `q` e paginazione retrograda `before`.
  - ADR di riferimento: `docs/adr/0005-bridge-agent.md`.

## 2. Pagine del cockpit e interfaccia (`system/interface/frontend-module.md`)
- Sezione **Assistente (Home)**:
  - Aggiornare lo stato del Bridge da "Post-MVP / UI ora e agente dopo" a "Costruito e attivo nel Runtime".
  - Specificare il contratto vincolante per messaggi (`Message`), azioni (`Action`), conversazioni (`GET /v1/read/bridge_conversations`), dettaglio thread (`GET /v1/read/bridge_conversation`), azioni in attesa (`GET /v1/read/bridge_actions`) e briefing (`GET /v1/read/briefing`).
  - Documentare gli eventi SSE real-time: `bridge.conversation`, `bridge.message`, `bridge.status`, `bridge.action`, `briefing.updated`, `tool.started`, `tool.finished`.

## 3. Ruoli e strumenti agenti (`system/agents/`)
- Aggiunta della scheda del **Bridge Agent**:
  - Ruolo: interlocutore di Luca, pari grado nell'ufficio, ponte verso tutti gli specialisti.
  - Modello predefinito: `my-combo`, effort `high`.
  - Tool di lettura: 18 tool compatti.
  - Tool di azione immediata: `add_watchlist`, `remove_watchlist`, `add_dossier_note`, `enqueue_task`, `refresh_data`, `upsert_annotation`, `strike_annotation`, `mark_inbox_read`.
  - Tool di proposta: `propose_action`.

## 4. Database e architettura (`system/foundation/architecture.md`)
- Schema migration 009:
  - `bridge_conversations`: thread multipli con titolo, stato `idle` / `thinking`, data creazione/aggiornamento e flag `archived`.
  - `bridge_messages`: messaggi (`text`, `agent_relay`, `action`, `error`) con riferimenti a entità (`refs_json`) e contesto di pagina/ticker (`context_json`).
  - `bridge_actions`: azioni su capitale proposte (`pending`), confermate, respinte, eseguite o fallite, con anteprima validata (`preview_json`).
  - `bridge_relay_subscriptions`: associazione temporanea per recapitare le risposte degli agenti al thread Bridge corretto.
  - `briefing_state`: memorizzazione persistente di `last_seen_ts` e cache delle sintesi generate dal modello.
