# Runtime unico: un processo sempre acceso, unico writer del DB, guidato da eventi

Il sistema gira dentro un **Runtime**: un solo processo sempre acceso che possiede il DB in scrittura, lo scheduler, i cicli degli agenti, l'order flow e la connessione al broker. CLI, frontend e bridge Telegram sono **client** del Runtime. Non costruiscono un Office proprio, non aprono il DB e non hanno credenziali broker. Parlano con il Runtime attraverso tre porte:

- **Comandi** tipizzati, validati, registrati nell'audit e idempotenti;
- **Letture** (read model);
- **Eventi** di dominio, emessi dopo ogni commit.

Il trasporto è HTTP per comandi e letture e SSE per gli eventi (FastAPI), su localhost o sulla rete Docker. Ogni modifica scrive nella stessa transazione una riga nella tabella append-only `events`, che fa da audit e da fonte per il replay SSE. Il DB resta l'unica fonte di verità. Lo stato in memoria del Runtime è solo una cache.

Il polling è eliminato:

- lo scheduler dorme fino alla prossima scadenza e si sveglia prima solo se arriva un evento;
- i fill arrivano dallo stream Alpaca `trade_updates`, con una riconciliazione all'avvio e a ogni riconnessione;
- refresh dati e retention diventano job a scadenza.

Più account broker significa un Runtime per account, ciascuno con DB e porta propri. Se il Runtime è spento, la CLI fallisce con un messaggio chiaro, perché non esiste un percorso offline. La migrazione è incrementale, a fette indipendenti, sopra l'Office esistente.

## Alternative scartate

- **Redis come layer centrale**: introduce una seconda fonte di verità da allineare con SQLite e un servizio in più da gestire, senza risolvere il problema dei molti writer. Dentro un solo processo bastano una cache in memoria e un bus `asyncio`/thread. Redis tornerà in discussione solo con più processi o più macchine, dietro la stessa interfaccia.
- **Watcher sul DB** (stato attuale: `Office.run()` ogni 0,5 s, sync ordini ogni 30 s): latenza e carico inutili. Le scritture dei processi esterni restano non validate e senza audit.
- **Socket Unix / gRPC**: il browser non li parla, quindi servirebbe comunque un gateway HTTP per la UI.
- **Runtime multi-account**: richiede `account_id` in tutto lo schema e limiti di rischio per account dentro un unico processo. Un Runtime per account isola il rischio e lascia lo schema invariato.
- **Letture offline dalla CLI**: un secondo percorso di codice da mantenere, per un beneficio di solo debug.
- **Audit solo nel log applicativo**: non è interrogabile e non permette alla UI di recuperare gli eventi persi dopo una disconnessione.

Decisione di Luca, 2026-11-20. Spec: `.scratch/core-runtime/spec.md`. Wiki: `wiki/system/foundation/decision-log.md`, `wiki/system/foundation/architecture.md`.
