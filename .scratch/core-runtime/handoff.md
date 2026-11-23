# Handoff: core runtime (single writer, event-driven) prima del frontend

> **Superato il 2026-11-20**: decisioni prese e progettazione chiusa. Vedi `docs/adr/0003-runtime-unico-writer-event-driven.md`, `spec.md` e `handoff-implementazione.md` in questa cartella.

Repo: `/home/luca/trading-agent`, branch `docs/agent-restart`. Wiki: `/home/luca/trading-agent-wiki`. Rispondi in italiano, conciso, azione prima della spiegazione. Commit + push di codice e wiki a fine lavoro.

## Perché esiste questo handoff

Il frontend (cockpit) è in pausa. Prima serve un **layer centrale** a cui fanno riferimento tutti i processi. Il codice di oggi non lo ha, e il lavoro richiede una riprogettazione profonda. Il frontend riparte da `/tmp/handoff-trading-agent-frontend.md` e da `PRODUCT.md` solo quando questo layer esiste.

## Cosa vuole l'utente (parole sue, sintetizzate)

- Un piccolo layer **resistente alle implementazioni future**: un "motore centrale" (o cache) che riceve gli input da tutte le interfacce (CLI, frontend, Telegram), da tutte le pipeline e dal backend, e **gestisce da solo letture e scritture nel DB**.
- Il DB resta la **fonte di verità** (come da wiki).
- **Niente processi watcher periodici** che ogni N secondi controllano il DB per accorgersi dei cambiamenti.

## Stato attuale (verificato nel codice, commit `803e1c9`)

- **Allineato alla wiki solo a metà.** `wiki/system/foundation/architecture.md` dice "DB come hub centrale, unica fonte di verità". Il DB è la fonte di verità, ma è anche l'unico canale tra i processi e non esiste uno strato applicativo davanti al DB.
- **Ogni processo è un motore intero.** Ogni comando della CLI (`interface/cli.py`) chiama `bootstrap.build_office()`: crea un `Office` completo, con client broker e LLM, e scrive direttamente nel DB (`office.db.append_message`, `enqueue_scheduled_task`, `order_flow.approve`, `halt.halt`).
- **Scrivono nel DB molti moduli:** `bootstrap.py`, `data/cache.py`, `data/refresh.py`, `tools/environment.py`, `workflows/office.py`, `workflows/cycle.py`, `execution/order_flow.py`, `execution/trade_manager.py`, `storage/retention.py`, `storage/registry.py`. `storage/office_db.py` ha 53 metodi e apre una connessione sqlite3 condivisa, in modalità WAL.
- **Polling ovunque:**
  - `Office.run()` (`workflows/office.py:646`) interroga il DB ogni **0,5 s** (`due_scheduled_tasks`) per accorgersi dei task, anche di quelli inseriti da altri processi (CLI).
  - `order_flow.sync_broker_orders()` interroga Alpaca ogni **30 s**: non c'è uno stream `trade_updates`.
  - `refresh_data` (ogni ora) e `run_retention` (ogni settimana) sono job programmati, non watcher: possono restare, ma vanno spostati sullo scheduler a scadenza.
- **Nessuna API HTTP.** `docs/dashboard.md` è obsoleto: cita `scripts/`, rimosso in `384362b`.
- La wiki (`wiki/system/interface/frontend-module.md`) chiede già "contratti applicativi stabili, non accesso diretto a repository interni sparsi", con validazione server-side, audit e conferme distinte per le azioni che toccano il capitale. Il codice di oggi non lo rispetta.

## Direzione proposta (da discutere con l'utente, non decisa)

1. **Core service a processo unico, unico writer del DB.** È l'unico processo che apre `OfficeDB` in scrittura. Contiene scheduler, cicli, order flow e broker. Espone:
   - **Command** tipizzati (approve/reject ordine, halt/resume, say, task, watchlist, config), validati e con audit;
   - **Query** (read model: portafoglio, ordini, trade, cicli, chat, inbox, health);
   - **Eventi** (stream di domain event emessi dopo ogni commit).
2. **Bus di eventi in-process** al posto del polling: ogni scrittura emette un evento dopo il commit. Lo scheduler si sveglia sul prossimo `due_ts`, oppure subito quando arriva un evento `task_enqueued`, invece di girare ogni 0,5 s.
3. **Trasporto verso i client**: HTTP (FastAPI) per command e query, SSE o WebSocket per gli eventi. CLI, frontend e bridge Telegram diventano **client sottili** del core, senza `Office` proprio e senza credenziali broker.
4. **Broker**: stream Alpaca `trade_updates` per fill e cancellazioni, con una riconciliazione all'avvio e alla riconnessione invece della sync ogni 30 s.
5. **"Cache"**: lo stato caldo in memoria nel core (portafoglio, halt, prezzi) va letto attraverso il core. Il DB resta la verità persistente; la cache non è mai fonte di verità.

## Decisioni aperte (da prendere con l'utente, non delegarle)

- Il core espone HTTP+SSE su localhost/Docker, oppure un altro IPC (socket Unix, gRPC)?
- La CLI deve funzionare anche a core spento (modalità offline in sola lettura sul DB) o fallisce?
- Multi-account broker: l'utente vuole più account selezionabili. Un core per account, oppure un core multi-account (account come dimensione di ordini, portafoglio e cicli)? Influisce sullo schema del DB.
- Audit: tabella di eventi/command append-only (event log), oppure solo log applicativo?
- Migrazione: refactor incrementale (prima la facade command/query sopra `Office`, poi il bus, poi i client) oppure riscrittura del boundary?

## Prossimi passi suggeriti

1. Rileggere con l'utente questa direzione: skill `grilling` o `codebase-design` (vocabolario deep module, seam).
2. Registrare la decisione come ADR (skill `domain-modeling`) e nella wiki (`wiki/system/foundation/decision-log.md`, `architecture.md`).
3. Scrivere una spec breve in `.scratch/core-runtime/spec.md`: interfacce command/query/event e piano di migrazione.
4. Implementare test-first (skill `tdd`), cominciando dalla facade command/query e dalla sostituzione del polling dello scheduler.
5. Aggiornare `docs/architecture.md`, `docs/office-engine.md`, `docs/dashboard.md`, `README.md`.
6. Poi riprendere il frontend: `/impeccable shape cockpit`, con il read model e gli eventi del core come fonte dati.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere i sorgenti, `graphify update .` dopo le modifiche al codice.
- Ignora `openbb-ui/` e `telegram-claude/` (sottoprogetti).
- Deleghe `claude -p`: solo modello `my-combo`, mai `free`.
- `PRODUCT.md` è confermato e committato: solo tema scuro, account broker selezionabili, nessuna modalità paper/live in UI. `docs/frontend.md:21` dice ancora "Clearly distinguish paper and live trading": va corretto (in attesa dell'ok dell'utente).
- Non committare `data/trading-agent.db*`, `nohup.out`, `.serena/`, `graphify-out/`, `frontend/tsconfig.tsbuildinfo`.
