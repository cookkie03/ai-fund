# Handoff: agenti del ticker e scheda del ticker (backend)

Repo `/home/luca/trading-agent`. Parti da `feat/cockpit-frontend` aggiornato, in un worktree o branch tuo (`ticker-agents-backend`). Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: test verdi, ruff pulito, `graphify update .`, commit e push sul tuo branch, non su `feat/cockpit-frontend` (l'unione la decide Luca).

**Coordinamento:** il backend del Portafoglio (branch `portafoglio-backend`) tocca `runtime/queries.py`, `runtime/commands.py`, `storage/office_db.py` e lo scenario di sviluppo. Se è già unito in `feat/cockpit-frontend`, parti da lì; altrimenti tieni le modifiche a quei file piccole e localizzate e segnala nel report i punti di possibile conflitto.

## Obiettivo

Implementare la decisione di `.scratch/ticker-agents/brief.md` (leggilo per primo): un livello intermedio di **Agenti del ticker** tra PM e specialist, e la **Scheda del ticker** (investment state) come documento persistente, strutturato e versionato, esposto dal Runtime al cockpit.

## Da leggere

- Wiki (`/home/luca/trading-agent-wiki/wiki/`): `system/orchestration/parallelism-design.md` (decisione a imbuto, alternativa A e B/C), `system/investment/investment-state-template.md` (campi, prima i CORE), `system/investment/state-schemas.md`, `system/investment/rating-scoring.md`, `system/foundation/ideas-log.md` ("Agente Single Ticker"), `system/agents/agent-memory.md`.
- Repo: `.scratch/agent-mvp/spec.md` (motore attuale), `docs/adr/0003-runtime-unico-writer-event-driven.md`, `docs/dashboard.md`, `workflows/office.py`, `workflows/cycle.py`, `tools/environment.py`, `tools/schemas.py`, `storage/office_db.py` (`ticker_state`), `config/office.toml`, `config/office_settings.py`, prompt degli agenti.

**Passo 0:** cerca nel codice e nella wiki ogni traccia già esistente dell'idea (valutatore, agente per ticker, scheda ticker, `research_state`) e riparti da quella invece di duplicarla. Riporta cosa hai trovato.

## Cosa costruire

1. **Ruoli.**
   - **Agente del ticker**: identità persistente `ticker:<SYM>` (es. `ticker:NVDA`), una per ogni ticker in portafoglio o in analisi, creata alla prima apertura di un ciclo sul ticker. Configurazione unica `[agents.ticker_agent]` in `config/office.toml` (endpoint, modello, effort). Esegue il Ciclo di analisi: scrive agli specialist nella chat del ticker, raccoglie le analisi, scrive tesi e coefficienti nella scheda, **sottopone una proposta** al PM. Non può creare ordini.
   - **Portfolio Manager**: riceve le proposte, le valuta con il contesto di portafoglio (posizioni, cassa, esposizione per settore, vincoli, altre proposte aperte) e decide: `accept` (con eventuale ridimensionamento), `defer` (con data di verifica), `reject`, `ask` (rimanda domande all'agente del ticker). Solo `accept` genera la Bozza deterministica → Risk Gate → coda di approvazione. Il PM continua ad aprire cicli (Scheduled task) e a ricevere i messaggi di Luca.
   - Specialist invariati. `subagent` invariato.
   - Regole esistenti preservate: Budget del ciclo, `max_parallel`, fusione degli Scheduled task, Rimando deterministico con avviso se fallisce l'agente del ticker o il PM, compattazione della chat a ogni ciclo, lezione di una riga sull'esito precedente (ora scritta nella scheda).
2. **Scheda del ticker.** Evolvi `ticker_state` in una scheda strutturata e versionata (tabelle o JSON versionato, scegli e motiva). Ogni fatto ha `author`, `ts`, `reference_date`, `confidence` (0–1 o null), `status` (`active` | `stale` | `superseded`). Scritta solo attraverso i tool degli agenti e i comandi del Runtime, mai a mano. Marcatura deterministica `stale` oltre una soglia configurabile per sezione. Lo storico delle versioni resta leggibile. `GET /v1/read/ticker_state` continua a funzionare (alias o adattamento) per il Terminale attuale.
3. **Tool degli agenti.** Agente del ticker: leggere e scrivere la scheda (tesi, pro/contro, catalizzatori, prossima verifica), scrivere agli specialist, `submit_proposal`. PM: leggere le proposte aperte e le schede, `decide_proposal`. Specialist: i tool attuali scrivono nelle loro sezioni della scheda. Tutti i tool registrano chiamate e costi come oggi.
4. **Comandi per Luca** (con `Idempotency-Key`, `X-Actor`): `add_dossier_note {ticker, text}` (nota firmata da Luca nella scheda, letta dagli agenti come parere di un collega senior); `decide_proposal` disponibile anche a Luca con `confirm:true` (stesso percorso del PM, Risk Gate sovrano).
5. **Eventi SSE** (tabella `events`, dal punto di scrittura reale): `dossier.updated {ticker, version, sections}`, `proposal.submitted`, `proposal.decided`, e `agent.status` anche per gli agenti del ticker.

## Contratto (vincolante: il frontend lo usa con questi nomi esatti)

Se lo cambi, aggiorna questo file e `docs/dashboard.md` nello stesso commit e scrivilo nel report. Percentuali come frazioni, timestamp ISO UTC.

- `GET /v1/read/agents`: a ogni elemento aggiungi `kind: "core" | "ticker"`, `ticker` (solo per `kind: "ticker"`, altrimenti `null`), `supervisor` (`"portfolio_manager"` per gli agenti del ticker, `null` per gli altri). I campi attuali restano invariati.
- `GET /v1/read/dossier?ticker=` →
  ```
  {ticker, version, updated_ts, updated_by, status: "idle"|"analyzing"|"proposed"|"approved"|"declined"|"monitoring",
   identity: {name, sector, industry, market_cap, currency, current_price, as_of},
   portfolio: {invested, qty, position_weight, avg_entry_price, unrealized_pnl, sector_exposure, cash_fraction},
   desks: [{agent, section, text, ts, reference_date, confidence, status}],
   thesis: {direction, conviction, pro: [str], contro: [str], time_horizon, catalysts: [{text, date}], next_check_date, author, ts} | null,
   proposal: {id, status, k_entry, k_stop, k_tp, entry_price, stop_price, target_price, sizing_fraction, risk_reward, submitted_ts} | null,
   risk: {verdict, rationale, guardrails: [{rule, ok, detail}]} | null,
   decisions: [{ts, actor, action, reason, cycle_id}],
   lessons: [{ts, text, exit_reason}],
   notes: [{id, author, text, ts}],
   stale_count}
  ```
- `GET /v1/read/dossier_history?ticker=&limit=` → `[{version, ts, author, sections_changed: [str]}]`
- `GET /v1/read/proposals?status=&ticker=&limit=` → `[{id, ticker, agent, status: "pending"|"accepted"|"deferred"|"rejected"|"asked", direction, conviction, sizing_fraction, risk_reward, submitted_ts, decided_ts, decided_by, reason, cycle_id}]`
- `GET /v1/read/dossiers?limit=` → riepilogo per l'Ufficio e le liste: `[{ticker, status, direction, conviction, proposal_status, updated_ts, stale_count, invested}]`

## Scenario di sviluppo

Estendi `scripts/dev_cockpit_scenario.py` / `dev_cockpit_server.py`: 4–6 agenti del ticker in stati diversi (in analisi, in attesa del PM, inattivi), schede popolate con contributi di più specialist e almeno un fatto `stale`, proposte `pending`, `accepted`, `deferred`, una nota di Luca, storico decisioni e lezioni. Mai usato in produzione.

## Verifica

Test-first (skill `tdd`). Test del motore con backend LLM a copione: ciclo dell'agente del ticker → proposta → decisione del PM → Bozza → Risk Gate; `defer` e `ask`; fallimento dell'agente del ticker (Rimando); due ticker in parallelo senza mescolare chat e schede; marcatura `stale`; versioning; eventi pubblicati solo al commit; `add_dossier_note` letta dall'agente al ciclo successivo. Poi smoke HTTP/SSE reale sul server di sviluppo (porta **8772**, `--db data/dev-cockpit-ticker-be.db`).

## Documentazione

Nuovo ADR `docs/adr/0004-agenti-del-ticker.md` (contesto, decisione, conseguenze), aggiornamento di `.scratch/agent-mvp/spec.md` dove cambia il comportamento, `docs/dashboard.md` (endpoint, comandi, eventi). Annota in `.scratch/ticker-agents/wiki-notes-backend.md` cosa registrare nella wiki (la scrive la sessione principale).

## Fuori scope

`frontend/`, screening dell'universo e coda di priorità automatica (lascia i punti di aggancio), workspace per ticker con file e git, RAG.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere i sorgenti; Serena per il codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non committare `data/*.db*`, `nohup.out`, `.serena/`, `graphify-out/` (salvo il grafo se già tracciato), `frontend/tsconfig.tsbuildinfo`.
