# Report Implementazione Core Runtime (S1–S8)

**Data**: 2026-11-20  
**Riferimento**: `.scratch/core-runtime/spec.md`, [ADR 0003](docs/adr/0003-runtime-unico-writer-event-driven.md)  
**Branch**: `docs/agent-restart`  
**Esito**: Completato e verificato (304 test offline superati, ruff 0 errori, DoD §13 soddisfatta).

---

## 1. Stato delle fette di implementazione

Tutte le fette previste dalla specifica sono state realizzate secondo approccio TDD (test-first), lasciando la suite verde ad ogni step:

| Fetta | Titolo | Commit | Descrizione e Verifiche |
|---|---|---|---|
| **S1** | Event log + in-process bus | `30a7d51` | Tabella `events` (migrazione 002 in SQLite), hook transazionali `on_commit` re-entranti in `OfficeDB.transaction()`, `EventLog` append-only e `EventBus` con code e listener sincroni. Verificato da `tests/runtime/test_events.py`. |
| **S2** | Facade comandi e letture in-process | `1b9668c` | Comandi pydantic tipizzati (`runtime/commands.py`), handler con serializzazione e idempotenza su `command.accepted` (`runtime/handlers.py`), query model DTO con SQLite `mode=ro` (`runtime/queries.py`). Regola `Say`→PM spostata nel domain layer. Verificato da `tests/runtime/test_commands.py` e `test_queries.py`. |
| **S3** | Scheduler event-driven e job | `cae6b52` | Loop event-driven a zero polling basato su `min(next_due_ts(), min(job.next_run()))` e `Waiter` astratto risvegliato da eventi di dominio (`task.enqueued`, `task.failed`, `halt.changed`, `runtime.stopped`). Registro job: `data_refresh`, `retention`, `market_analyst_fixed`, `expire_pending`, `release_queued`. Rimosso `Office.run(poll_interval)`. Verificato da `tests/runtime/test_scheduler.py`. |
| **S4** | Eventi dai processi interni | `4145b42` | Iniezione `event_log` in `SystemHalt` (`halt.changed`), `OrderFlow` (`order.created/approved/rejected`), `TradeManager` (`trade.opened/closed`), `Office` (`task.delivered`, `cycle.opened`), `CycleRunner` (`cycle.closed`). Verificato da `tests/runtime/test_internal_events.py`. |
| **S5** | Trasporto HTTP, SSE e single-writer lock | `5618bec` | App FastAPI (`runtime/http.py`) con rotte `/v1/health`, `/v1/commands/{name}`, `/v1/read/{name}`, `/v1/events` (SSE con replay da `Last-Event-ID`/`?after=` e keepalive `: ping`). Autenticazione Bearer obbligatoria su bind non-loopback. Lock esclusivo OS `<db>.lock` via `fcntl.flock` contro istanze concorrenti. Verificato da `tests/runtime/test_http.py`. |
| **S6** | CLI client sottile | `dbb5c4a` | `interface/cli.py` migrato a client HTTP puro su `RuntimeClient` (`interface/client.py`). A Runtime offline la CLI esce pulita con codice 2 e messaggio esplicativo. Rimossi tutti gli import di `build_office` o `OfficeDB` in `interface/`. Verificato da `tests/interface/test_cli.py` e `test_client.py`. |
| **S7** | Broker stream e TradeManager | `c8dba50` | `AlpacaTradeUpdateStream` in thread background (`execution/alpaca_stream.py`). `OrderFlow.apply_broker_update` gestisce fill di entrata (`trade.opened`) e uscita TP/SL (`trade.closed`) collegati al `TradeManager`. Riconciliazione broker su startup e reconnect. Rimosso `order_sync_interval`. Verificato da `tests/execution/test_broker_stream.py`. |
| **S8** | Docker, docs e allineamento wiki | *In commit corrente* | Aggiornato `compose.engine.yaml` con healthcheck su `/v1/health` e porta 8765. Aggiornati `Dockerfile.engine`, `docs/architecture.md`, `docs/office-engine.md`, `docs/dashboard.md`, `README.md`. Wiki adiacente sincronizzata (`hot-cache.md`, `log.md`, `implementation-status.md`, `project-board.md`). |

---

## 2. Verifica §13 Definizione di Fatto (DoD)

1. **Suite di test e linting**:
   - `uv run pytest`: **304 passed**, 0 failed, 2 skipped in 28.8s.
   - `uv run ruff check .`: **0 issues**.
2. **Nessuna creazione DB/Office fuori da `runtime/`**:
   - `git grep "build_office"` restituisce solo chiamate interne a `runtime/core.py` (`Runtime.from_settings()`) e ai test di bootstrap.
   - Nessun modulo in `interface/` importa `OfficeDB` o `build_office`.
3. **Zero Polling & Polling residui**:
   - `poll_interval` e `order_sync_interval` eliminati dal codice operativo.
   - `sync_broker_orders` richiamato esclusivamente nella riconciliazione (`reconcile_broker`, avvio e reconnect dello stream).
4. **Smoke test locale e interazione stream**:
   - `trading-agent run` avvia uvicorn su `127.0.0.1:8765`, prende il lock esclusivo ed avvia lo scheduler su thread dedicato.
   - Client CLI esegue comandi via HTTP con emissione eventi immediata sul bus.
   - I test su SSE con replay e streaming (`tests/runtime/test_http.py`) confermano ricezione di eventi in tempo reale.
5. **Documentazione e Wiki sincronizzate**:
   - Tutti i documenti tecnici nel repo (`docs/`) e nel vault Obsidian (`trading-agent-wiki/`) aggiornati con distinzione chiara tra implementato/verificato e roadmap successiva (fetta S9 fuori perimetro, pronta per avvio successivo).

---

## 3. Prossimi Passi (Roadmap)

Con la conclusione delle fette S1–S8, il Core Runtime è stabile e pronto per il merge. La fetta successiva S9 (timeframe globale `bar_timeframe`, trailing stop continuo su barre, ingestione Alert esterni) potrà partire sui punti di aggancio già predisposti (`runtime/jobs.py`, `IngestAlert`).
