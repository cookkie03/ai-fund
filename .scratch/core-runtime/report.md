# Report Implementazione Core Runtime (S1–S8) e Correzioni Review (R1–R12)

**Data**: 2026-11-20  
**Riferimento**: `.scratch/core-runtime/spec.md`, `.scratch/core-runtime/review.md`, [ADR 0003](docs/adr/0003-runtime-unico-writer-event-driven.md)  
**Branch**: `docs/agent-restart`  
**Esito**: 336 test offline superati, 2 saltati; ruff senza errori. Nessuna verifica Alpaca reale in questa sessione.

---

## 1. Stato delle fette di implementazione (S1–S8)

Tutte le fette previste dalla specifica sono state realizzate secondo approccio TDD (test-first), lasciando la suite verde ad ogni step:

| Fetta | Titolo | Commit | Descrizione e Verifiche |
|---|---|---|---|
| **S1** | Event log + in-process bus | `7ec2ce3` | Tabella `events` (migrazione 002 in SQLite), hook transazionali `on_commit` re-entranti in `OfficeDB.transaction()`, `EventLog` append-only e `EventBus` con code e listener sincroni. Verificato da `tests/runtime/test_events.py`. |
| **S2** | Facade comandi e letture in-process | `1b9668c` | Comandi pydantic tipizzati (`runtime/commands.py`), handler con serializzazione e idempotenza su `command.accepted` (`runtime/handlers.py`), query model DTO con SQLite `mode=ro` (`runtime/queries.py`). Regola `Say`→PM spostata nel domain layer. Verificato da `tests/runtime/test_commands.py` e `test_queries.py`. |
| **S3** | Scheduler event-driven e job | `cae6b52` | Loop event-driven a zero polling basato su `min(next_due_ts(), min(job.next_run()))` e `Waiter` astratto risvegliato da eventi di dominio (`task.enqueued`, `task.failed`, `halt.changed`, `runtime.stopped`). Registro job: `data_refresh`, `retention`, `market_analyst_fixed`, `expire_pending`, `release_queued`. Rimosso `Office.run(poll_interval)`. Verificato da `tests/runtime/test_scheduler.py`. |
| **S4** | Eventi dai processi interni | `4145b42` | Iniezione `event_log` in `SystemHalt` (`halt.changed`), `OrderFlow` (`order.created/approved/rejected`), `TradeManager` (`trade.opened/closed`), `Office` (`task.delivered`, `cycle.opened`), `CycleRunner` (`cycle.closed`). Verificato da `tests/runtime/test_internal_events.py`. |
| **S5** | Trasporto HTTP, SSE e single-writer lock | `5618bec` | App FastAPI (`runtime/http.py`) con rotte `/v1/health`, `/v1/commands/{name}`, `/v1/read/{name}`, `/v1/events` (SSE con replay da `Last-Event-ID`/`?after=` e keepalive `: ping`). Autenticazione Bearer obbligatoria su bind non-loopback. Lock esclusivo OS `<db>.lock` via `fcntl.flock` contro istanze concorrenti. Verificato da `tests/runtime/test_http.py`. |
| **S6** | CLI client sottile | `dbb5c4a` | `interface/cli.py` migrato a client HTTP puro su `RuntimeClient` (`interface/client.py`). A Runtime offline la CLI esce pulita con codice 2 e messaggio esplicativo. Rimossi tutti gli import di `build_office` o `OfficeDB` in `interface/`. Verificato da `tests/interface/test_cli.py` e `test_client.py`. |
| **S7** | Broker stream e TradeManager | `c8dba50` | `AlpacaTradeUpdateStream` in thread background. `OrderFlow.apply_broker_update` gestisce fill di entrata (`trade.opened`) e uscita TP/SL (`trade.closed`) collegati al `TradeManager`. Riconciliazione broker su startup e reconnect. Rimosso `order_sync_interval`. Verificato da `tests/execution/test_broker_stream.py`. |
| **S8** | Docker, docs e allineamento wiki | `5639a72` | Aggiornato `compose.engine.yaml` con healthcheck su `/v1/health` e porta 8765. Aggiornati `Dockerfile.engine`, `docs/architecture.md`, `docs/office-engine.md`, `docs/dashboard.md`, `README.md`. Wiki adiacente sincronizzata (`hot-cache.md`, `log.md`, `implementation-status.md`, `project-board.md`). |

---

## 2. Scelte architetturali e deviazioni rispetto alla spec

1. **Collocazione e astrazione Stream Broker (`runtime/broker_stream.py`)**:
   - Conforme a spec §8 e §13, definito il protocollo `BrokerUpdateStream` e l'adapter `AlpacaTradeUpdateStream` in `runtime/broker_stream.py`.
   - `execution/alpaca_stream.py` re-importa e riesporta le classi per mantenere piena retrocompatibilità senza duplicazione.
2. **Isolamento transazioni e chiamate di rete (2-phase submit)**:
   - `Runtime.execute` non avvolge più l'intero handler in un'unica transazione SQLite immediata. Le scritture locali avvengono in transazioni dedicate prima e dopo la chiamata esterna di rete al broker.
   - Prima del submit lo stato locale diventa `submitting` con `client_order_id`; la rete opera fuori dalla transazione. Su errore l'esito resta incerto in `submitting`: la riconciliazione cerca il broker per `client_order_id`, senza inviare nuovamente. Anche un rifiuto certo resta in attesa di riconciliazione, perché il contratto broker non distingue gli errori definitivi.
3. **`RefreshData` asincrono con HTTP 202**:
   - Conforme a spec §5, `RefreshData` delega il prefetch dati a un thread worker in background e risponde immediatamente 202 con `{"status": "accepted"}`. Al termine del download, il worker emette l'evento `data.refreshed` nel bus ed event log.
4. **Persistenza job basata su Event Log**:
   - Invece di introdurre una tabella SQL addizionale, `_get_last_run` e `_record_job_run` utilizzano l'append-only log esistente leggendo gli eventi `job.ran` con subject `job:<name>`.

---

## 3. Correzioni della Review (R1–R12)

Tutti i problemi identificati nella review (`.scratch/core-runtime/review.md`) sono stati affrontati con approccio TDD (test che fallisce prima e passa dopo la correzione):

| Problema | Titolo | Commit | Scelte prese e Verifiche |
|---|---|---|---|
| **R1** | Configurazione stream e riconciliazione all'avvio | `3e028f0` | Centralizzata lettura credenziali (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_TRADING_URL`) tramite `get_alpaca_credentials()`. Esecuzione forzata di `reconcile_broker()` all'avvio del Runtime anche in assenza di stream. `HealthDTO` espone `broker_configured` e stato stream. Verificato da `tests/runtime/test_r1_broker_config_startup.py`. |
| **R2** | Chiamate di rete broker fuori dalla transazione DB | `3e60b01`, `9f0655d` | Submit a due fasi; errore ambiguo conservato in `submitting` e ricerca per `client_order_id`. Smoke: il broker accetta, la risposta va in timeout e la riconciliazione ritrova l'ordine. `RefreshData` risponde 202 ed emette `data.refreshed` successivamente. |
| **R3** | Robustezza stream Alpaca e riconnessione | `d04cb41` | Aggiunto loop di riconnessione con backoff esponenziale in `AlpacaTradeUpdateStream`. Esecuzione del callback di riconciliazione ad ogni (ri)connessione. Proprietà `connected` reale e calcolo di `paper` dall'URL di trading. Verificato da `tests/runtime/test_r3_stream_robustness.py`. |
| **R4** | Creazione Trade da riconciliazione offline | `4e9d03f` | `sync_broker_orders` instrada i fill rilevati tramite `apply_broker_update`, generando `trade.opened` e record in `trades` per gli ordini eseguiti a Runtime spento. Confronto con posizioni del broker per chiudere trade i cui TP/SL sono scattati offline (`trade.closed`). Verificato da `tests/execution/test_r4_reconciliation_trades.py`. |
| **R5** | Scadenze reali dei job e persistenza esecuzioni | `28d399f` | Rimossi timer fissi: `expire_pending` calcola la deadline minima dei pending (o None se assenti), `release_queued` si risveglia alla prossima apertura del mercato broker (o None se assenti), `market_analyst_fixed` punta alla prossima sessione premarket. Persistito `last_run` tramite eventi `job.ran`. Verificato da `tests/runtime/test_r5_job_deadlines_persistence.py`. |
| **R6** | Eliminazione eventi duplicati | `bcd5521` | Eliminata emissione duplicata di `halt.changed`, `order.approved` e `order.rejected` dagli handler HTTP/comandi: l'evento viene generato esclusivamente dal domain layer (`SystemHalt`, `OrderFlow`). Verificato da `tests/runtime/test_r6_no_duplicate_events.py`. |
| **R7** | Riesecuzione Risk Gate all'approvazione ordine | `099385c` | `handle_approve_order` costruisce un `RiskGateContext` fresco tramite `office.build_risk_gate_context()`. Risolto bug di falsy default su `cash == 0`. Verificato da `tests/runtime/test_r7_riskgate_on_approval.py`. |
| **R8** | SSE subscribe-before-replay e bridge asincrono | `6cd04de` | Sottoscrizione al bus prima del replay storico con de-duplicazione per ID (nessun buco temporale). Bridge asincrono `loop.call_soon_threadsafe` + `asyncio.Queue` senza thread bloccati. Chiusura connessione su overflow coda per forzare replay client. Verificato da `tests/runtime/test_r8_sse_robustness.py`. |
| **R9** | Prevenzione busy-loop dello scheduler | `c083239` | Se `run_once()` non consegna task e la prossima scadenza è nel passato (task non consegnabile o filtrato dal cursore), lo scheduler applica un backoff minimo di 1.0s evitando di risvegliarsi a 0.0s in busy loop. Verificato da `tests/runtime/test_r9_scheduler_busy_loop.py`. |
| **R10** | Lock di processo anticipato e rimozione log residuo | `346803a` | Acquisizione del lock OS `<db>.db.lock` in `interface/cli.py` prima di costruire l'Office o migrare il DB; uscita pulita con exit code 1 e messaggio d'errore senza traceback. Rimossa dicitura `(poll interval: 0.5s)`. Verificato da `tests/interface/test_r10_early_lock_and_poll_log.py`. |
| **R11** | Conferme CLI, autore messaggi e token HMAC | `a9eddcf` | Aggiunto flag `-y`/`--yes` e richiesta di conferma interattiva per `halt`, `resume` e `orders approve`. Comando `Say` registra autore come `user` (actor `cli` nell'evento). Endpoint read migrati a funzioni sincrone `def` in threadpool. Confronto token con `hmac.compare_digest`. Verificato da `tests/interface/test_r11_cli_confirmation_and_author.py`. |
| **R12** | Protocollo BrokerUpdateStream e completamento report | `cbbcac5` | Formalizzazione del protocollo `BrokerUpdateStream` e conformità di `FakeBrokerStream`; correzione hash di commit e documentazione scelte/deviazioni. |

---

## 4. Verifica Finale di Conformità (§13 DoD e Verifica Review)

1. **Suite di test completa**:
   - `uv run pytest`: **336 passed**, 0 failed, 2 skipped in 14.40s.
   - `uv run ruff check .`: **0 issues**.
2. **Regole architetturali**:
   - Nessun import di `OfficeDB` o `build_office` al di fuori di `runtime/` e dei test di bootstrap.
   - `poll_interval` e `order_sync_interval` completamente eliminati dal codice operativo.
   - Broker stream protetto e isolato; riconciliazione centralizzata all'avvio e al reconnect.
3. **Repository e documentazione**:
   - Repository `trading-agent` pulito e sincronizzato con `origin/docs/agent-restart`.
   - Repository `trading-agent-wiki` pulito e sincronizzato con `origin/main`.

## 5. Secondo giro

| Voce | Commit | Scelta e verifica |
|---|---|---|
| N1 | `0cc261a`, `7ba4e89` | La riconciliazione legge `qty` dal `SafeBrokerReader` senza chiudere Trade con posizione aperta. Se manca la posizione, usa solo il prezzo effettivo di una gamba bracket collegata (richiesta Alpaca `nested=True`); altrimenti `reconciled_unknown`, prezzo nullo e avviso in Inbox. Se la lettura delle posizioni fallisce, non chiude i Trade. |
| N2 | `356f9d0`, `f296161` | Dopo un errore di invio cerca subito l'ordine per `client_order_id`. Un errore ambiguo resta `submitting` se il lookup non lo trova; solo una risposta 4xx strutturata e definitiva produce `rejected`. |
| N3 | `c285308` | Effetto locale e audit condividono la transazione; il test forza un errore sull'audit e verifica il rollback. Approvazione, halt, riconciliazione e refresh mantengono transazioni separate per non trattenere il lock SQLite durante I/O esterno. |
| N4 | `b7df168` | `order.created` e `order.status_changed` svegliano lo scheduler; regressioni verificate su entrambi gli eventi. |
| N5 | — | Rinviato: occorre condividere la selezione dei task consegnabili fra Office e scheduler senza saltare task pronti. Rimane il backoff da 1 s. |
| N6 | `23e23cc` | CLI e bootstrap condividono il percorso canonico, anche con un symlink. Una `runtime_factory` personalizzata deve ancora rispettare il percorso configurato. |

Verifica offline: 350 test passati, 2 saltati, Ruff pulito. Nessuna prova con Alpaca reale.
