# Review S1–S8 del Runtime e handoff per il goal di correzione

Data: 2026-11-20. Base della review: `5639a72` (branch `docs/agent-restart`). Riferimenti: `spec.md`, `report.md`, ADR 0003.

## Goal (da incollare in `/goal`)

> Correggi i problemi R1–R12 elencati in `.scratch/core-runtime/review.md`, test-first. Ogni problema deve avere un test che fallisce prima della correzione e passa dopo. Hai finito quando suite e ruff sono verdi, lo smoke del §«Verifica finale» passa, `report.md` contiene un §«Correzioni review» con hash e scelte prese, e codice e wiki sono pushati senza ahead/behind.

Regole operative: identiche a `handoff-implementazione.md` (AGENTS.md, skill `tdd`, un commit per problema o gruppo coerente, `my-combo` per le deleghe, file da non committare). S9 resta fuori.

## Cosa è verificato

- `uv run pytest`: 304 passed, 2 skipped; `uv run ruff check .`: pulito. Rieseguiti in questa review dopo aver ricostruito il venv locale, che era corrotto (`uv sync --reinstall`).
- **Smoke con Office di test** (broker e LLM finti, DB temporaneo, porta 8799):
  - CLI `watchlist add/list`, `say`, `halt`, `resume` e `cycles list` funzionano via HTTP;
  - il task del PM viene consegnato subito (`task.delivered`, `cycle.opened`, `cycle.closed`), senza polling;
  - lo stream SSE riceve `command.accepted`, `message.appended`, `task.enqueued` e gli altri eventi;
  - un secondo Runtime sullo stesso DB viene rifiutato.
- Non verificato: Runtime con Alpaca paper reale, stream `trade_updates` reale, container Docker.

## Problemi trovati

### Bloccanti: il ciclo di vita degli ordini reali non funziona

**R1 — Lo stream broker non parte mai.** `runtime/core.py:100-101` legge `APCA_API_KEY_ID` e `APCA_API_SECRET_KEY`, ma il progetto (`.env`, `bootstrap.py:337`, `brokers/alpaca.py:68`) usa `ALPACA_API_KEY` e `ALPACA_SECRET_KEY`. Lo stream resta quindi `None`, e da lì:
- nessun fill diventa Trade;
- nessuno stato ordine si aggiorna;
- **nessuna riconciliazione avviene mai**, perché il loop di sync ogni 30 s è stato rimosso e la riconciliazione parte solo da `stream.start()`.

Correzione:
- leggere le stesse variabili del resto del progetto, da un'unica funzione di config;
- riconciliare all'avvio del Runtime anche senza stream;
- se le credenziali ci sono ma lo stream non parte, `health()` deve dirlo.

**R2 — Effetti sul broker dentro la transazione DB.** `Runtime.execute` avvolge ogni handler in `BEGIN IMMEDIATE`. Gli handler che fanno chiamate di rete (`ApproveOrder` → submit del bracket, `Halt` → cancel degli ordini, `ReconcileBroker`, `RefreshData`) hanno due problemi:
- tengono il lock di scrittura per tutta la durata della rete, e bloccano scheduler e cicli;
- se qualcosa fallisce dopo il submit, il rollback cancella la traccia locale di un ordine **già vivo al broker**, che nessuna riconciliazione vedrà mai.

Correzione: la transazione copre solo le scritture locali, e la chiamata di rete sta fuori. Per gli ordini lo schema è: scrittura locale `approved` + evento in tx → submit → seconda tx con l'esito. In caso di errore resta uno stato locale riconciliabile (`submitting`, con `client_order_id`). `RefreshData` diventa davvero asincrono: risponde 202 e il risultato arriva con l'evento `data.refreshed`, come da spec §5.

**R3 — Stream fragile.** `execution/alpaca_stream.py` ha tre difetti:
- se `TradingStream.run()` termina, il thread esce senza riprovare e lo stream resta morto;
- le riconnessioni interne di alpaca-py non chiamano la riconciliazione, quindi gli eventi persi non vengono recuperati;
- `broker_stream_connected` diventa `True` appena il thread parte, non quando la connessione è realmente stabilita.

Inoltre `paper` viene letto da un `settings.broker` che non esiste, quindi vale sempre `True`. Questo contraddice la decisione «paper o live solo dalle credenziali»: con credenziali live lo stream si collegherebbe all'endpoint paper.

Correzione:
- loop di riconnessione con backoff e riconciliazione a ogni (ri)connessione;
- stato di connessione reale (`broker_stream.connected` / `disconnected`);
- `paper` derivato da `ALPACA_TRADING_URL`, come in `brokers/alpaca.py`.

**R4 — La riconciliazione non crea i Trade.** `sync_broker_orders()` aggiorna solo lo stato degli ordini locali `submitted` e non emette eventi. Un fill avvenuto a Runtime spento (entrata, oppure TP/SL di una gamba) lascia l'ordine `filled` senza Trade, o un Trade aperto che al broker è già chiuso.

Correzione: la riconciliazione passa dallo stesso percorso di `apply_broker_update`, costruendo update sintetici dallo stato del broker, oppure confronta le posizioni del broker con i Trade aperti. Deve emettere gli eventi e restare idempotente.

### Importanti

**R5 — I job sono timer periodici, non scadenze.** `runtime/jobs.py` usa intervalli fissi:
- `expire_pending` ogni 15 min, `release_queued` ogni 5 min, `market_analyst_fixed` ogni 30 min;
- `last_run` vive solo in memoria, quindi se il Runtime si riavvia più spesso di una volta a settimana la **retention non gira mai**, mentre il refresh dati riparte a ogni avvio.

Correzione, come da spec §7:
- `expire_pending` alla prima scadenza reale di un ordine pending;
- `release_queued` alla prossima apertura del mercato (calendario broker);
- `market_analyst_fixed` alla prossima attivazione fissa;
- ultima esecuzione persistita (tabella `job_runs` o eventi `job.ran` nell'Event log).

**R6 — Eventi duplicati.** `halt.changed` (verificato via SSE), `order.approved` e `order.rejected` vengono emessi sia dall'handler sia dal dominio (`SystemHalt`, `OrderFlow`). Correzione: emette solo il dominio, l'handler no. Test: un comando produce esattamente un evento di dominio.

**R7 — Risk Gate non rieseguito all'approvazione.** `handle_approve_order` chiama `order_flow.approve(order_id)` senza `ctx`, quindi il Risk Gate non gira con il portafoglio attuale: un pending vecchio può violare i limiti di oggi (posizioni, cassa, settore). Era così anche nella vecchia CLI, ma la spec §5 lo richiede. Correzione: costruire il `RiskGateContext` fresco nell'handler.

**R8 — SSE.** Tre difetti:
- il replay (`since`) avviene prima della `subscribe`, quindi gli eventi committati nel mezzo si perdono;
- un client lento perde eventi in silenzio, mentre la spec chiede di chiudere la connessione così che il client faccia replay;
- ogni client SSE occupa un thread del threadpool (`to_thread(sub.get, 15)`).

Correzione: prima `subscribe`, poi replay, poi deduplica per `id`; chiusura della connessione su coda piena; bridge asincrono (`loop.call_soon_threadsafe` + `asyncio.Queue`) come da spec §9.

**R9 — Possibile busy-loop dello scheduler (da confermare con un test).** Se esiste un task `pending` scaduto che `run_once` non consegna (per esempio filtrato da `DueCursor`), `next_due_ts()` resta nel passato e `waiter.wait(0)` gira a vuoto. Correzione: calcolare la prossima scadenza sui soli task consegnabili, oppure applicare un backoff minimo per i task scaduti non consegnati, con un test che lo dimostri.

### Minori

**R10 — Lock e avvio.**
- Il secondo Runtime costruisce l'Office e migra il DB **prima** di prendere il lock, poi esce con un traceback. Il lock va preso per primo, con un messaggio pulito e exit code ≠ 0.
- L'avvio stampa ancora `poll interval: 0.5s`, residuo del vecchio loop: va rimosso.

**R11 — Client e trasporto.**
- `Say` registra come autore l'actor (`cli`, `ui`) invece di `user`: gli agenti vedono il messaggio come scritto da «cli». L'autore deve restare `user`, con l'actor nell'evento.
- `halt`, `resume` e `orders approve` dalla CLI inviano `confirm=true` senza chiedere niente: servono una conferma interattiva o `--yes`.
- Le letture sincrone SQLite girano dentro handler `async`: vanno in `def` o in `to_thread`.
- Il confronto del token va fatto con `hmac.compare_digest`.

**R12 — Report e struttura.** In `report.md`:
- gli hash dei commit non corrispondono al log (S1 è `7ec2ce3`, non `30a7d51`; S8 è `5639a72`);
- mancano i paragrafi «scelte prese» e «deviazioni» richiesti dall'handoff.

Lo stream sta in `execution/alpaca_stream.py` invece che in `runtime/broker_stream.py`, senza il protocollo `BrokerUpdateStream` previsto dalla spec: va spostato, oppure la deviazione va documentata.

## Verifica finale del goal di correzione

1. Suite e ruff verdi.
2. Smoke con Office di test (script tipo `scratchpad/smoke/run_smoke.py`: `build_test_office` + `Runtime` + `main(["run", "--port", …], runtime_factory=…)`):
   - un solo `halt.changed` per comando;
   - secondo Runtime rifiutato prima di toccare il DB;
   - SSE con `?after=` senza buchi durante comandi concorrenti.
3. Test con broker e stream finti:
   - fill a Runtime spento, poi avvio ⇒ Trade aperto o chiuso correttamente;
   - submit che riesce seguito da un errore ⇒ ordine riconciliabile, non perso;
   - stream che cade ⇒ riconnessione e riconciliazione.
4. Facoltativo, solo se le chiavi paper funzionano: avvio reale con `ALPACA_*` e `health()` con `broker_stream_connected=true`. Nessun ordine.

## Dopo le correzioni (fuori da questo goal)

- **S9**: timeframe globale, trailing e Alert (spec §14). Prima di ordini reali, ritaratura dei coefficienti `k`.
- **Telegram**: il bridge diventa client di `RuntimeClient`.
- **Frontend**: riparte usando le letture e `/v1/events` come fonte dati.
- **Smoke reale**: LLM e Alpaca paper sul Minisforum, con il container `engine` aggiornato.
