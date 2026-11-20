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

---

# Secondo giro — verifica delle correzioni R1–R12 (2026-11-20, base `f44fa20`)

## Goal (da incollare in `/goal`)

> Correggi N1–N3 di `.scratch/core-runtime/review.md` (§«Secondo giro»), test-first. Fai anche N4–N6 se restano semplici. Ogni test deve usare le **forme reali di produzione**: `SafeBrokerReader`, che restituisce dizionari con `qty`, e il wiring di `bootstrap.build_office`/`_lazy_init_alpaca_broker` dove possibile, non mock con attributi inventati. Hai finito quando suite e ruff sono verdi, la riproduzione di N1 qui sotto non chiude più il Trade, `report.md` ha un §«Secondo giro» con hash e scelte prese, e codice e wiki sono pushati senza ahead/behind.

## Verificato

- 336 test passati, 2 saltati; ruff pulito.
- Smoke con Office di test: un solo `halt.changed` per comando (R6 ok); secondo Runtime rifiutato con exit 1 e messaggio pulito (R10 ok); `say` produce consegna immediata e ciclo completo; nessun log di «poll interval».
- Controllate nel codice e risolte: R1 (credenziali `ALPACA_*` centralizzate, riconciliazione all'avvio), R3 (riconnessione con backoff, `paper` derivato dall'URL), R5 (scadenze reali, `job.ran` persistiti), R6, R7, R8, R10, R11, R12.

## Problemi nuovi

### N1 — Bloccante: la riconciliazione chiude tutti i Trade aperti

`OrderFlow.sync_broker_orders()`, parte 2, legge la quantità delle posizioni con `p.get("quantity", 0)`. In produzione però il reader è `SafeBrokerReader` (`bootstrap.py:_lazy_init_alpaca_broker`), che restituisce dizionari con la chiave **`qty`**. Ogni posizione risulta quindi a 0, e **a ogni riconciliazione** (avvio, riconnessione dello stream, comando `ReconcileBroker`) ogni Trade aperto viene chiuso nel DB anche se la posizione è ancora aperta al broker. I test passavano perché usavano mock con `quantity`.

Riproduzione, eseguita in questa review: `build_test_office(broker_reader=SafeBrokerReader(reader con AAPL qty=10))` + `record_entry_fill`, poi `sync_broker_orders()`. Risultato: Trade chiuso, `exit_price=150.0` (= entrata), `exit_reason='tp'`.

Il bug corrompe anche i dati: la chiusura avviene **inventata**, al prezzo di entrata e con motivo «tp». Il log dei Trade è il registro delle performance (decisione Q68).

Correzione:
- normalizzare le posizioni con un solo modello (`qty`), in un solo punto;
- chiudere un Trade solo se il broker conferma davvero che la posizione non c'è più;
- usare il fill reale di uscita (ordine gamba TP/SL chiuso, o attività FILL del conto). Se non è ricostruibile, motivo `reconciled_unknown` + voce in Inbox, mai «tp» con prezzo di entrata;
- se la lettura delle posizioni fallisce, non toccare i Trade.

### N2 — Alto: un errore di rete all'invio può lasciare un ordine orfano al broker

In `_submit_order_locked`, qualsiasi eccezione di `submit_bracket` imposta lo stato `rejected`. Con un timeout l'ordine può essere già stato accettato da Alpaca: localmente risulta rifiutato, e la riconciliazione cerca solo `submitted`/`submitting` con `broker_order_id IS NOT NULL`, quindi non lo vedrà mai. Lo stato `submitting` introdotto da R2 viene sovrascritto e non serve allo scopo.

Correzione:
- in caso di eccezione, chiamare `broker.find_by_client_id(client_order_id)`: se l'ordine esiste → `submitted` con il suo id; se il broker non è raggiungibile → resta `submitting` senza `broker_order_id`;
- la riconciliazione deve cercare anche i `submitting` per `client_order_id`;
- `rejected` solo per un rifiuto esplicito del broker (errore 4xx).

### N3 — Medio: l'audit del comando non è più atomico con l'effetto

Dopo R2, l'handler gira in autocommit e `command.accepted` viene scritto in una transazione successiva. Se il processo cade tra le due, resta l'effetto senza audit, e un retry con la stessa `Idempotency-Key` riesegue il comando: per esempio `Say` duplica il messaggio. La spec §5 chiedeva un'unica transazione.

Correzione: gli handler solo locali (`EnqueueTask`, `Say`, watchlist, `MarkInboxRead`, `IngestAlert`, `Reject`) tornano in un'unica transazione con l'audit. Lo split resta solo per i comandi con chiamate di rete, e la deviazione va documentata nel report.

### Minori

- **N4**: lo scheduler non si sveglia su `order.created` e `order.status_changed`, quindi le scadenze di `expire_pending`/`release_queued` calcolate su un ordine nuovo possono slittare fino al risveglio successivo (≤ 1 h, grazie a `data_refresh`). Correzione: aggiungerli alla lista di wake.
- **N5**: il backoff di R9 è un polling a 1 s finché resta un task scaduto non consegnabile. Correzione: escludere quel task dal calcolo della scadenza, o marcarlo, invece di ripetere il controllo ogni secondo.
- **N6**: `interface/cli.py` prende il lock sul percorso DB letto dalla config, non su quello del DB effettivamente aperto dal Runtime. Sono due fonti diverse, coincidenti in produzione ma non con `runtime_factory`. Correzione: un'unica funzione che risolve il percorso DB, usata sia dal lock sia da `build_office`.

## Lezione per i prossimi goal

I test con mock costruiti a mano hanno nascosto N1. Per tutto ciò che legge dati del broker, almeno un test deve passare dal wiring di produzione (`SafeBrokerReader` e gli adapter reali con client finto).
