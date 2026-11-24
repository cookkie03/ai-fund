# Handoff: Bridge agent e letture dell'Assistente (backend)

Repo `/home/luca/trading-agent`, branch **`assistente-frontend`** (la branch della pagina, già creata da `main` e pushata; contiene backend e frontend dell'Assistente). Lavora nel checkout principale su quella branch, oppure in un tuo worktree con un branch derivato da essa. Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: test verdi, ruff pulito, `graphify update .`, commit e push su `assistente-frontend`. Non aprire la PR e non unire su `main`: lo fa la sessione principale dopo il frontend.

**Coordinamento:** in parallelo una sessione di frontend lavora in un worktree proprio e tocca solo `frontend/`. Tu non toccare `frontend/`. Il contratto qui sotto è vincolante per entrambi.

## Obiettivo

Implementare il **Bridge agent** descritto in `.scratch/assistente/brief.md` (leggilo per primo): un agente vero del Runtime, interlocutore di Luca, con conversazioni multiple, tool di lettura su tutto l'ufficio, messaggi agli agenti, comandi della UI (quelli che toccano capitale solo come azione da confermare), più la lettura del **briefing** per la home.

## Da leggere

- Wiki (`/home/luca/trading-agent-wiki/wiki/`): `system/interface/frontend-module.md` (pagine del cockpit, collega jolly), `system/foundation/decision-log.md` (2026-11-20 e 2026-11-22), `system/agents/` (ruoli e memoria degli agenti; cerca «Configuration & State Agent», il vecchio nome del Bridge).
- Repo: `AGENTS.md`, `docs/adr/0003-runtime-unico-writer-event-driven.md`, `docs/adr/0004-agenti-del-ticker.md`, `docs/dashboard.md`, `docs/office-engine.md`, `.scratch/agent-mvp/spec.md`, `runtime/commands.py`, `runtime/handlers.py`, `runtime/core.py`, `runtime/queries.py`, `runtime/http.py`, `runtime/events.py`, `runtime/jobs.py`, `workflows/office.py`, `tools/environment.py`, `tools/schemas.py`, `storage/office_db.py`, `config/office.toml`, `config/office_settings.py`, `prompts/`.

**Passo 0:** cerca nel codice e nella wiki ogni traccia dell'idea (Bridge, «Configuration & State Agent», topic `cockpit`, inbox) e riparti da quella. Riporta cosa hai trovato.

## Cosa costruire

1. **Agente `bridge`.** Configurazione `[agents.bridge]` in `config/office.toml` (endpoint, modello, effort `high`, budget giornaliero), prompt `prompts/bridge.md` (in italiano: collega di Luca, conciso, cita le fonti con riferimenti, distingue fatti da opinioni, non promette esiti, ricorda che il Risk Gate decide). Costi e chiamate in `llm_calls` come gli altri; compare in `GET /v1/read/agents` con `kind: "core"`, `supervisor: null`.
2. **Turni del Bridge.** Un messaggio di Luca (`bridge_say`) mette in coda un turno; il turno gira nel worker del Runtime (mai nel thread HTTP), con budget per turno e limite di passi di tool. Un solo turno attivo per conversazione; i messaggi arrivati durante un turno entrano nel turno successivo. `bridge_stop` interrompe il turno al passo successivo. Errori del modello o del budget diventano un messaggio `kind: "error"` leggibile, mai un turno appeso.
3. **Tool del Bridge** (registrati e loggati come gli altri, con chiamate visibili in `tool_calls` con `agent = "bridge"`):
   - **Lettura**: portafoglio e posizioni, ordini, trade, performance, limiti di rischio e loro storico, schede e proposte, agenti e loro stato, chat di qualunque agente (paginata), chiamate ai tool, costi, watchlist, annotazioni del grafico, prezzi e indicatori (stesse letture dell'ambiente degli agenti), inbox, eventi recenti, briefing. Risultati compatti: il Bridge riassume, non incolla tabelle intere.
   - **Messaggi agli agenti**: `message_agent {agent, topic, text}` scrive nella chat dell'agente con autore `bridge` e nota «per conto di Luca». Se l'agente risponde in quella chat, la risposta rientra nella conversazione del Bridge come messaggio `kind: "agent_relay"` e fa partire un turno di sintesi. Il messaggio al PM segue la regola attuale di `Say` (crea uno Scheduled task).
   - **Azioni senza capitale**, eseguite subito con attore `bridge` e citate nella risposta: `add_watchlist`, `remove_watchlist`, `add_dossier_note` (firmata «Bridge per Luca»), `enqueue_task`, `refresh_data`, `upsert_annotation`, `strike_annotation`, `mark_inbox_read`.
   - **Azioni con capitale**, solo proposte: `propose_action {command, payload, summary}` con `command` in `approve_order`, `reject_order`, `close_position`, `modify_exit`, `decide_proposal`, `halt`, `resume`, `update_risk_limits`. Il Runtime valida subito il payload con il modello Pydantic del comando e, dove esiste, fa il `dry_run`/preview (es. `PositionExits`, Risk Gate) per mostrare a Luca l'esito previsto; salva l'azione `pending`. Niente esecuzione senza `bridge_action_decide`.
4. **Briefing.** Lettura deterministica di cosa è successo da `since` (default: l'ultima `mark_briefing_seen`, altrimenti 24 h): trade eseguiti, ordini in attesa di approvazione, proposte in attesa e decise, alert, Halt/Resume, variazione del valore del portafoglio, schede cambiate, errori o fallimenti degli agenti, modifiche ai limiti. La `summary_text` la scrive il Bridge (un turno breve, cache per `since` e invalidata da nuovi eventi rilevanti, con costo tracciato); se manca o il budget è finito, `summary_text: null` e le voci bastano.
5. **Comandi per Luca** (con `Idempotency-Key`, `X-Actor`, envelope `{ok, data, reasons}`):
   - `bridge_say {conversation_id: int|null, text, context: {page, ticker, ref: {type, id}}|null}` → `data: {conversation_id, message_id}`. Con `conversation_id: null` crea la conversazione; il titolo provvisorio sono le prime parole, poi il Bridge lo sostituisce con uno breve dopo il primo turno.
   - `bridge_rename_conversation {conversation_id, title}`, `bridge_archive_conversation {conversation_id, archived: bool}`, `bridge_stop {conversation_id}`.
   - `bridge_action_decide {action_id, decision: "confirm"|"dismiss", confirm: bool}`: `confirm` deve essere `true` per `decision: "confirm"`. Esegue il comando originale **dallo stesso handler** con attore `luca` (via Bridge), rifacendo tutte le validazioni (Halt, Risk Gate, limiti, stato corrente: se nel frattempo la posizione è chiusa o l'ordine non è più in attesa, rifiuta con il motivo). L'esito torna nella conversazione e il Bridge lo commenta in un turno breve. È un comando di rete se lo è il comando originale (`is_network_cmd` in `runtime/core.py`).
   - `mark_briefing_seen {ts}`.
6. **Eventi SSE** (tabella `events`, dal punto di scrittura reale, pubblicati al commit): `bridge.message {conversation_id, message}`, `bridge.status {conversation_id, status: "thinking"|"tool"|"idle", tool: str|null}`, `bridge.action {conversation_id, action}` (creata o cambiata di stato), `bridge.conversation {conversation}` (creata, rinominata, archiviata), `briefing.updated {since}`. Già che ci sei, emetti `tool.started` e `tool.finished` per tutti gli agenti se manca solo poco (oggi esiste solo l'esito): utile all'Ufficio e allo stato del Bridge.

## Contratto (vincolante: il frontend usa esattamente questi nomi)

Se lo cambi, aggiorna questo file e `docs/dashboard.md` nello stesso commit e scrivilo nel report. Percentuali come frazioni, timestamp ISO UTC.

```
Message = {id, conversation_id, author: "luca"|"bridge"|<agent id>, kind: "text"|"agent_relay"|"action"|"error",
           text, ts, context: {page, ticker, ref}|null,
           refs: [{type: "ticker"|"order"|"position"|"proposal"|"cycle"|"agent"|"trade", id, label}],
           action: Action|null}
Action  = {id, command, payload, summary, capital: true, status: "pending"|"confirmed"|"dismissed"|"executed"|"failed",
           preview: {ok, reasons: [str], detail}|null, result_reasons: [str], decided_ts|null, decided_by|null}
```

- `GET /v1/read/bridge_conversations?limit=&q=&archived=` → `[{id, title, created_ts, updated_ts, message_count, status: "idle"|"thinking", archived, last_message: {author, text, ts}|null, pending_actions}]`, ordinate per `updated_ts` decrescente; `q` cerca in titolo e testo.
- `GET /v1/read/bridge_conversation?id=&limit=&before=` → `{id, title, created_ts, updated_ts, status, archived, messages: [Message]}` con gli ultimi `limit` messaggi in ordine cronologico (default 100); `before` = id per paginare indietro.
- `GET /v1/read/bridge_actions?status=` → `[Action & {conversation_id}]` (per mostrare le azioni in attesa anche fuori dalla conversazione).
- `GET /v1/read/briefing?since=` →
  ```
  {since, generated_ts, summary_text|null, summary_ts|null,
   portfolio: {value, change, change_fraction}|null,
   counts: {trades, orders_pending, proposals_pending, proposals_decided, alerts, agent_errors},
   items: [{id, type: "trade"|"order_pending"|"proposal_pending"|"proposal_decided"|"alert"|"halt"|"resume"|"dossier"|"agent_error"|"risk_limits",
            ts, title, detail|null, ticker|null, ref: {type, id}|null, severity: "info"|"attention"|"critical"}]}
  ```
  `items` dal più recente, massimo 50; `id` stabile (per «chiedi al Bridge di questa voce»).

Lo stato vivo del pannello laterale il frontend lo compone dalle letture esistenti (`portfolio`, `positions`, `health`, `agents`, `proposals`): nessun endpoint nuovo.

## Scenario di sviluppo

Estendi `scripts/dev_cockpit_scenario.py` / `dev_cockpit_server.py`: 3–4 conversazioni del Bridge (una con un `agent_relay` dal Technical, una con un'azione `pending` di `close_position` con preview, una con un'azione `executed` e una `dismissed`, una archiviata), un briefing con voci di ogni tipo e `summary_text`. In sviluppo il Bridge risponde con un **backend LLM a copione** (deterministico, nessuna chiamata di rete) così che `bridge_say` produca davvero un turno con una chiamata ai tool, un messaggio e, su parole chiave tipo «chiudi», un'azione proposta. Mai usato in produzione.

## Verifica

Test-first (skill `tdd`), backend LLM a copione:
- `bridge_say` crea conversazione e turno; il turno legge con i tool e risponde; `bridge.status` passa da `thinking` a `idle`.
- Due conversazioni in parallelo non mescolano messaggi né contesto; un secondo messaggio durante un turno entra nel successivo.
- `message_agent` scrive nella chat dell'agente; la risposta dell'agente torna come `agent_relay`; il messaggio al PM crea lo Scheduled task.
- Azione senza capitale eseguita subito con attore `bridge`; azione con capitale resta `pending` con preview; `bridge_action_decide` senza `confirm:true` rifiutato; con conferma esegue dallo stesso handler; Halt e Risk Gate la bloccano come farebbero dalla UI; stato cambiato nel frattempo → `failed` con motivo; `dismiss` non esegue nulla.
- Il Bridge non può chiamare direttamente un comando con capitale (test negativo sul registro dei tool).
- Budget finito → messaggio `error`, nessun turno appeso; `bridge_stop` interrompe.
- Briefing: voci corrette da `since`, `mark_briefing_seen` sposta il default, `summary_text: null` senza budget.
- Eventi pubblicati solo al commit; idempotenza dei comandi.
Poi smoke HTTP/SSE reale sul server di sviluppo (porta **8774**, `--db data/dev-cockpit-assistente-be.db`): conversazione, turno, azione proposta e confermata, eventi visti con `curl -N /v1/events`.

## Documentazione

ADR `docs/adr/0005-bridge-agent.md` (contesto, decisione, conseguenze: perché le azioni con capitale passano da una conferma e dallo stesso handler), `docs/dashboard.md` (endpoint, comandi, eventi), `docs/office-engine.md` dove cambia il motore. Annota in `.scratch/assistente/wiki-notes-backend.md` cosa registrare nella wiki (la scrive la sessione principale).

## Fuori scope

`frontend/`, memoria a lungo termine delle preferenze di Luca, voce, notifiche, Telegram, pagine Notizie e Configurazioni.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere i sorgenti; Serena per il codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non committare `data/*.db*`, `nohup.out`, `.serena/`, `graphify-out/` (salvo il grafo se già tracciato), `frontend/tsconfig.tsbuildinfo`.
- Comandi: `.venv/bin/python -m pytest -q -p no:cacheprovider`, `.venv/bin/ruff check .`.
