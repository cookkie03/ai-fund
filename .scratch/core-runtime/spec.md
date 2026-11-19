# Spec — Runtime unico (single writer, event-driven)

Stato: **progettazione approvata da Luca il 2026-11-20, non implementata**. Decisione: `docs/adr/0003-runtime-unico-writer-event-driven.md`. Base di codice: branch `docs/agent-restart`, commit `6d228b3`.

## 1. Obiettivo

Un solo processo, il **Runtime**, è sempre acceso, unico writer del DB e unico detentore delle credenziali broker. CLI, frontend e bridge Telegram diventano client sottili che usano tre porte: Comandi, Letture ed Eventi. Si eliminano i watcher periodici: lo scheduler a 0,5 s e la sync ordini a 30 s.

```
 CLI ─┐                       ┌─────────────── RUNTIME (processo unico) ──────────────┐
 UI  ─┼── HTTP: comandi ────► │ Runtime.execute → handler → DB (tx) + riga in events  │
 Tg  ─┘   HTTP: letture  ───► │ Runtime.query   → connessione DB in sola lettura      │
   ▲                          │ EventBus ◄── after-commit                             │
   └──── SSE /events ◄────────│ Scheduler (dorme fino a scadenza / evento)            │
                              │ Office (cicli) · OrderFlow · TradeManager             │
                              │ BrokerStream (Alpaca trade_updates)                   │
                              └───────────────────────────────┬───────────────────────┘
                                                        SQLite WAL (verità)
```

## 2. Decisioni prese (Luca, 2026-11-20)

| Tema | Scelta |
|---|---|
| Trasporto | HTTP (FastAPI) per comandi e letture, SSE per gli eventi |
| CLI a Runtime spento | Fallisce con un messaggio chiaro; nessuna modalità offline |
| Multi-account | Un Runtime per account: DB, porta e container propri; schema invariato |
| Audit | Tabella append-only `events` nel DB, scritta nella stessa transazione della modifica |
| Migrazione | Incrementale, a fette indipendenti e testate, sopra l'Office esistente |
| Cache/Redis | Nessun Redis. Lo stato caldo sta in memoria nel Runtime e non è mai fonte di verità |

## 3. Stato attuale (verificato nel codice, `6d228b3`)

- **Ogni comando CLI costruisce un Office completo** (`interface/cli.py` → `bootstrap.build_office()`) e scrive direttamente nel DB. Parte della logica di dominio sta nella CLI: `say` verso il PM accoda anche uno Scheduled task (`interface/cli.py:74-102`).
- **Polling**: `Office.run()` (`workflows/office.py:646`) esegue `run_once()` ogni 0,5 s; dentro lo stesso loop girano `sync_broker_orders()` ogni 30 s, `refresh_data()` ogni ora e `run_retention()` ogni settimana.
- **DB**: `storage/office_db.py` usa una sola connessione `sqlite3` in WAL, con `check_same_thread=False`, `RLock` e `transaction()` (`BEGIN IMMEDIATE`). Le scritture fuori da `transaction()` vanno in autocommit.
- **Funzioni mai chiamate in produzione** (verificato con grep): `TradeManager.record_entry_fill`, `record_exit_fill`, `on_price`, `OrderFlow.expire_pending`, `release_queued`, `Office.ingest_external_alert`. Oggi i fill non diventano Trade, gli ordini pending non scadono e quelli in coda non partono all'apertura del mercato. Questa spec ne collega quattro (§7, §8); `on_price` e le fonti di Alert restano fuori perimetro (§11).
- **Dipendenze**: `pyproject.toml` non include FastAPI, uvicorn o httpx.
- **Docker**: `compose.engine.yaml` avvia un servizio `engine` senza porta esposta.

## 4. Moduli (nuovo package `runtime/`)

Interfacce piccole, implementazione profonda. I nomi sono vincolanti; i dettagli interni sono liberi.

| Modulo | Interfaccia | Responsabilità |
|---|---|---|
| `runtime/events.py` | `Event`, `EventLog.append(type, subject, payload, actor, command_id=None) -> Event`, `EventLog.since(after_id, limit) -> list[Event]`, `EventBus.subscribe() -> Subscription`, `EventBus.publish(event)` | Tabella `events`, notifica after-commit, fan-out thread-safe in-process |
| `runtime/commands.py` | Modelli Pydantic dei comandi (§5) e `CommandResult` | Validazione dell'input; nessuna logica |
| `runtime/handlers.py` | Un handler per comando: `(ctx, cmd) -> CommandResult` | Logica di dominio, inclusa quella spostata dalla CLI; usa Office, OrderFlow, Halt e OfficeDB |
| `runtime/queries.py` | `ReadModel` con un metodo per lettura (§6) | Letture su una connessione in sola lettura (`file:…?mode=ro`, una per thread); restituisce DTO serializzabili |
| `runtime/scheduler.py` | `Scheduler(clock, waiter, jobs, …)`, `.run()`, `.stop()`, `.wake()` | Trigger engine senza polling (§7) |
| `runtime/jobs.py` | `Job(name, next_run(now) -> datetime \| None, run(now))` | Lavori a scadenza (§7) |
| `runtime/broker_stream.py` | Protocollo `BrokerUpdateStream` con `run(on_update, on_connect)`; adapter Alpaca e fake | Stream `trade_updates` e riconciliazione (§8) |
| `runtime/core.py` | `Runtime.start()`, `.stop()`, `.execute(cmd, actor, command_id) -> CommandResult`, `.read: ReadModel`, `.subscribe(after_id) -> Iterator[Event]` | Composizione, single-writer lock, ciclo di vita dei thread |
| `runtime/http.py` | `create_app(runtime) -> FastAPI` | Trasporto (§9); nessuna logica |
| `interface/client.py` | `RuntimeClient(base_url, token)`, `RuntimeUnavailable` | Client HTTP usato dalla CLI e, in futuro, da Telegram |

**Regola di seam:** i client conoscono solo `RuntimeClient`, o l'HTTP per la UI. Solo `runtime/core.py` crea `OfficeDB` in scrittura. `bootstrap.build_office()` resta la factory delle dipendenze interne, chiamata solo da `Runtime`.

## 5. Comandi

Ogni comando ha un `command_id` (UUID generato dal client) e un `actor` (`cli`, `ui`, `telegram`, `scheduler`, `broker`, `runtime`). `execute` funziona così:

1. valida il modello; se fallisce scrive `command.rejected` e restituisce un errore 422;
2. **idempotenza**: se `command_id` esiste già, restituisce il risultato salvato senza eseguire di nuovo;
3. esegue l'handler; per quanto possibile, scritture ed eventi stanno in una sola transazione;
4. scrive `command.accepted`, con il risultato nel payload, nella stessa transazione.

Un errore di dominio (per esempio un ordine non pending) è un risultato `ok=false` con le ragioni, non un'eccezione, ed è registrato come `command.rejected`.

| Comando | Campi | Note |
|---|---|---|
| `EnqueueTask` | `agent`, `ticker`, `reason`, `when_ts?` | Ex `trading-agent task`; evento `task.enqueued` |
| `Say` | `agent`, `chat`, `text` | Ex `say`. La regola "messaggio al PM ⇒ Scheduled task" si sposta nell'handler; eventi `message.appended` (+ `task.enqueued`) |
| `AddWatchlist` / `RemoveWatchlist` | `ticker`, `note?` | `watchlist.changed` |
| `ApproveOrder` | `order_id`, `confirm: Literal[True]` | **Tocca il capitale**: senza `confirm=true` → 422. Ri-esegue il Risk Gate (comportamento esistente) |
| `RejectOrder` | `order_id`, `reason` | `order.rejected` |
| `Halt` | `cancel_open: bool = True`, `confirm: Literal[True]` | `halt.changed` |
| `Resume` | `confirm: Literal[True]` | `halt.changed` |
| `ReconcileBroker` | — | Ex `orders sync` + `portfolio sync`: riconciliazione manuale ordini e portafoglio |
| `RefreshData` | `kinds?`, `force` | Asincrono: risposta `accepted` immediata, risultato con l'evento `data.refreshed` |
| `MarkInboxRead` | `item_id` | `inbox.changed` |
| `IngestAlert` | `ticker`, `source`, `reason`, `data` | Seam per le future fonti di Alert; chiama `Office.ingest_external_alert` |

`config check` **non** è un comando: legge solo env e settings e resta locale nella CLI, senza DB e senza Office, perché serve proprio quando il Runtime non parte.

## 6. Letture (read model)

DTO Pydantic serializzabili, una lettura per metodo, tutte paginate dove serve:

`health()` (account label, Runtime version, halt, stato stream broker, prossima scadenza dello scheduler, dimensione DB, `last_event_id`) · `portfolio()` (ultimo snapshot) · `orders(status?, limit)` · `order(id)` (con gli `order_events`) · `trades(status?, ticker?, limit)` · `cycles(ticker?, status?, limit)` · `cycle(id)` (con i messaggi) · `chat(agent, topic, limit)` · `ticker_state(ticker)` · `watchlist()` · `inbox(unread_only, limit)` · `scheduled_tasks(status?, limit)`.

Le query SQL oggi dentro la CLI (`cycles list/show`, `chat show`, `orders list`, `trades list`) si spostano qui, e la CLI le formatta soltanto.

## 7. Eventi, bus e scheduler

### Tabella `events` (migrazione nuova in `OfficeDB._migrate`)

```sql
CREATE TABLE events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         TEXT NOT NULL,
  type       TEXT NOT NULL,
  actor      TEXT NOT NULL,
  subject    TEXT,              -- es. 'order:12', 'ticker:AAPL', 'cycle:7'
  command_id TEXT,
  payload    TEXT NOT NULL      -- JSON
);
CREATE INDEX events_type_ts ON events(type, ts);
CREATE UNIQUE INDEX events_command_once ON events(command_id)
  WHERE command_id IS NOT NULL AND type = 'command.accepted';
```

Append-only: nessun UPDATE o DELETE, e la retention non tocca questa tabella nel MVP.

### Regola di emissione

`EventLog.append` inserisce la riga. Dentro `OfficeDB.transaction()` la notifica al bus è registrata con un hook `on_commit`, da aggiungere a `OfficeDB`, e parte solo dopo il commit; un rollback la scarta. Fuori da una transazione (autocommit) la notifica parte subito dopo l'insert. Nessun evento viene pubblicato per una scrittura non committata.

### Catalogo degli eventi

`command.accepted` · `command.rejected` · `task.enqueued` · `task.delivered` · `task.failed` · `task.merged` · `message.appended` · `cycle.opened` · `cycle.closed` · `ticker_state.changed` · `watchlist.changed` · `order.created` (pending/queued) · `order.approved` · `order.rejected` · `order.submitted` · `order.status_changed` · `order.expired` · `trade.opened` · `trade.closed` · `portfolio.synced` · `halt.changed` · `inbox.added` · `inbox.changed` · `data.refreshed` · `runtime.started` · `runtime.stopped` · `broker_stream.connected` · `broker_stream.disconnected`.

Gli eventi dei processi interni (Office, OrderFlow, TradeManager, Halt) passano da un `EventLog` iniettato nei costruttori, opzionale con default no-op per non rompere i test esistenti.

### Scheduler senza polling

```
loop:
  if halted: aspetta senza timeout un wake (halt.changed / stop)
  esegui il lavoro scaduto: run_once() esistente + job scaduti
  next = min(db.next_due_ts(), min(job.next_run(now)))
  waiter.wait(timeout = next - now, oppure None se non c'è nulla)
```

- `OfficeDB.next_due_ts()` è un metodo nuovo: `MIN(COALESCE(next_attempt_ts, when_ts))` sui task `pending`.
- **Wake**: gli eventi `task.enqueued`, `task.failed` (retry), `halt.changed` e `stop()` chiamano `scheduler.wake()`. Nessun timeout di sicurezza periodico.
- `Waiter` è astratto (`threading.Event` in produzione, fake nei test) e il `clock` è iniettato: i test non dormono mai.
- **Job a scadenza** (`runtime/jobs.py`), che sostituiscono gli intervalli in `Office.run`:
  - `data_refresh`: ogni ora;
  - `retention`: settimanale, seguito da `check_db_size`, oggi chiamato a ogni `run_once`;
  - `market_analyst_fixed`: alla prossima attivazione fissa, oggi `ensure_fixed_market_analyst_activations` a ogni passata;
  - `expire_pending`: alla prima scadenza di un ordine pending;
  - `release_queued`: alla prossima apertura del mercato, dal clock del broker.
- `Office.run(poll_interval)` viene rimosso e `trading-agent run` avvia il Runtime.

## 8. Broker: stream invece di sync

- `AlpacaTradeUpdateStream` usa `alpaca.trading.stream.TradingStream` di alpaca-py 0.44 (`paper=True` dalla config) e `subscribe_trade_updates`, in un thread dedicato.
- Ogni update chiama un metodo nuovo, `OrderFlow.apply_broker_update(update)`, che:
  - aggiorna lo stato dell'ordine, scrive l'`order_event` ed emette `order.status_changed`;
  - collega il `TradeManager`: il fill della gamba di entrata chiama `record_entry_fill` (`trade.opened`), il fill di take profit o stop loss chiama `record_exit_fill` (`trade.closed`);
  - gestisce `canceled`, `expired`, `rejected`, `replaced` e `partial_fill` secondo `_BROKER_STATUS_MAP`.
- Se lo stesso update arriva due volte, il risultato non cambia (idempotenza su `broker_order_id` + `event` + `timestamp`).
- **Riconciliazione** all'avvio e a ogni `on_connect` (riconnessione): `sync_broker_orders()` esistente e sync del portafoglio. Il loop ogni 30 s sparisce.
- Il fake stream per i test sta in `tests/fakes/`. Il test reale resta opzionale con il marker `integration`.

## 9. Trasporto HTTP + SSE

- `POST /v1/commands/{name}` con body = comando e header `Idempotency-Key: <command_id>` e `X-Actor`. Risponde 200 con il `CommandResult`, 202 per `RefreshData`, 422 per input non valido, 409 per un conflitto di dominio se utile, 503 se il Runtime è in arresto.
- `GET /v1/read/{name}?…` per le letture del §6.
- `GET /v1/events` (SSE): ogni messaggio ha `id: <events.id>`, `event: <type>`, `data: <json>`. Con l'header `Last-Event-ID` o il parametro `?after=` il server invia prima il replay da `EventLog.since`, poi il live. Un keep-alive `: ping` ogni 15 s serve solo alla connessione HTTP, non controlla il DB.
- `GET /v1/health`: è `ReadModel.health()`; lo usa anche il healthcheck Docker.
- **Bind**: `127.0.0.1:8765` di default (`TRADING_AGENT_API_HOST`, `TRADING_AGENT_API_PORT`). Con `TRADING_AGENT_API_TOKEN` impostato, tutti gli endpoint richiedono `Authorization: Bearer`; il token è obbligatorio se il bind non è loopback.
- **Concorrenza**: uvicorn sul thread principale. Gli endpoint sync girano nel threadpool di FastAPI e chiamano `Runtime.execute`, serializzato dal lock di `OfficeDB` e da un lock comandi. Scheduler, worker dei cicli (`max_parallel` esistente) e broker stream girano in thread propri. L'SSE fa da ponte dal bus ai client con `loop.call_soon_threadsafe` e una coda per client, limitata: se un client è troppo lento si chiude la sua connessione e lui riprende con il replay.
- **Single writer**: all'avvio il Runtime prende un lock esclusivo, `fcntl.flock` su `<db>.lock`; un secondo `run` sullo stesso DB fallisce subito.
- **Dipendenze nuove**: `fastapi`, `uvicorn`, `httpx` (client CLI e `TestClient`). Versioni bloccate in `uv.lock`.

## 10. Client

- **CLI** (`interface/cli.py`): tutti i comandi tranne `run` e `config check` usano `RuntimeClient`. Indirizzo da `--runtime URL` o da `TRADING_AGENT_RUNTIME_URL`, default `http://127.0.0.1:8765`. Se non risponde, la CLI esce con codice 2 e il messaggio `Runtime non attivo su <url>: avvialo con 'trading-agent run' (o docker compose up).` Output e flag restano quelli di oggi.
- **Frontend**: fuori da questo lavoro. Usa le stesse rotte, e lo stream `/v1/events` alimenta il cockpit. La selezione dell'account è la selezione dell'URL del Runtime.
- **Telegram** (`telegram-claude/`, sottoprogetto): fuori da questo lavoro. Il contratto è `RuntimeClient`.

## 11. Fuori perimetro

Frontend, migrazione del bridge Telegram, stream prezzi e trailing stop (`on_price` resta non collegato: serve una decisione su stream dati contro job sulle barre), fonti di Alert reali, Runtime multi-account, PostgreSQL, Redis.

## 12. Piano di migrazione (fette)

Ogni fetta parte test-first (skill `tdd`), lascia la suite verde e ha un commit proprio. L'ordine è vincolante solo dove indicato.

| # | Fetta | Accettazione (test) |
|---|---|---|
| S1 | **Event log + bus**: migrazione `events`, hook `on_commit` in `OfficeDB`, `EventLog`, `EventBus` | Evento visibile ai subscriber solo dopo il commit; rollback ⇒ nessun evento e nessuna riga; `since(after_id)` restituisce l'ordine corretto; fan-out a N subscriber da thread diversi |
| S2 | **Facade comandi/letture** in-process (`Runtime.execute`, `ReadModel`), sopra Office/OrderFlow esistenti. Dipende da S1 | Un test per comando, con gli stessi comportamenti di `tests/interface/test_cli.py`; idempotenza (`command_id` ripetuto ⇒ un solo effetto); `ApproveOrder` senza `confirm` ⇒ rifiutato e registrato; `command.accepted`/`rejected` nella stessa tx; regola `Say`→PM spostata nell'handler |
| S3 | **Scheduler event-driven** + job. Dipende da S1 | Con clock e waiter fake: nessun risveglio senza eventi o scadenze; `EnqueueTask` sveglia subito; risveglio esatto a `when_ts`; halt blocca fino a `Resume`; retry di un task fallito al suo `next_attempt_ts`; i job girano alla loro scadenza; `Office.run`/`poll_interval` rimossi |
| S4 | **Eventi dai processi interni** (Office, OrderFlow, Halt, inbox, portfolio). Dipende da S1 | Un ciclo smoke (`tests/integration/test_office_smoke.py`) produce la sequenza attesa `cycle.opened … cycle.closed`, `order.created` |
| S5 | **HTTP + SSE + single-writer lock**; `trading-agent run` avvia il Runtime. Dipende da S2–S4 | `TestClient`: rotte comandi e letture; SSE con replay da `Last-Event-ID` poi live; token obbligatorio fuori da loopback; secondo Runtime sullo stesso DB rifiutato |
| S6 | **CLI client sottile**. Dipende da S5 | `test_cli.py` riscritto contro un Runtime in-process via `TestClient`/transport httpx; Runtime spento ⇒ exit 2 con il messaggio; nessun import di `build_office` in `interface/` |
| S7 | **Broker stream** + `apply_broker_update` + collegamento del TradeManager + riconciliazione + job `expire_pending`/`release_queued`. Dipende da S1, S3 | Fake stream: fill di entrata ⇒ Trade aperto; fill TP/SL ⇒ Trade chiuso; update duplicati idempotenti; la riconnessione esegue la riconciliazione; `order_sync_interval` rimosso |
| S8 | **Docker e documentazione** | `compose.engine.yaml`: porta `127.0.0.1:8765:8765` e healthcheck su `/v1/health`. Aggiornati `docs/architecture.md`, `docs/office-engine.md`, `docs/dashboard.md` (riscritto come API del Runtime), `README.md`, wiki (log, board, hot-cache, implementation-status) |

## 13. Definizione di fatto

- `uv run pytest` verde e `uv run ruff check .` pulito.
- `grep` conferma che fuori da `runtime/` e dai test nessun modulo crea `OfficeDB` o chiama `build_office`, e che `poll_interval`, `order_sync_interval` e `sync_broker_orders` compaiono solo nella riconciliazione.
- Smoke locale con broker fake o paper: `trading-agent run` in un terminale; `curl -N localhost:8765/v1/events` in un altro; `trading-agent say portfolio_manager AAPL "ciao"` produce `command.accepted`, `message.appended` e `task.enqueued` sullo stream, e il task parte senza attesa.
- Documentazione e wiki aggiornate come in S8, con la distinzione tra cosa è implementato e cosa è verificato.
