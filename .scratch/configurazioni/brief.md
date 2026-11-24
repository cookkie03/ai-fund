# Brief: pagina Configurazioni

Decisioni di Luca del 2026-11-24, che completano quella del 2026-11-20 (wiki `system/interface/frontend-module.md`: «Configurazioni: agenti, modelli, prompt, schedule, budget, provider, account broker, DB e retention, salute del Runtime»). Branch della pagina: **`configurazioni-frontend`** (backend e frontend insieme, PR verso `main` con CI verde).

## Decisioni

1. **Impostazioni modificabili e versionate**, come i limiti di rischio del Portafoglio: modifica con motivo, validazione contro limiti, storico e ripristino di una versione. Il Runtime applica dal vivo ciò che può; il resto è marcato «vale dal prossimo riavvio» e la pagina lo dice prima della conferma.
2. **Prompt degli agenti modificabili**, con versioni, diff rispetto alla precedente, motivo e ripristino; il nuovo prompt vale dal ciclo successivo.
3. **Chiavi API modificabili dalla pagina** (OmniRoute, Alpaca, provider dati): solo in scrittura. Il Runtime le salva lato server fuori dal repository e dal DB, non le rimanda mai al frontend (solo «impostata / non impostata», ultime 4 cifre, data, esito dell'ultimo test di connessione), e registra nell'audit chi e quando, mai il valore.
4. **Collocazione per coerenza** (scelta lasciata a me da Luca): ogni informazione vive dove si usa, Configurazioni non duplica.
   - In **Configurazioni**: Agenti (modello, endpoint, effort, budget, prompt), Provider e chiavi (OmniRoute, broker, provider dati e loro test), Mercato e orari (orari, timeframe, cadenza dei cicli, `max_parallel`, limiti degli Scheduled task, modalità di approvazione degli ordini), Dati e archivio (retention, dimensione del DB, soglia di avviso, backup), Salute del Runtime (job e ultima esecuzione, errori, versioni, connessioni SSE).
   - **Altrove**, con collegamento dall'indice di Configurazioni: limiti di rischio → Portafoglio («Rischio e vincoli»); fonti delle notizie → Notizie; watchlist → Terminale; costi e token degli agenti → Ufficio; Halt → barra in alto.

## Regole che non cambiano

Runtime unico writer, comandi con `Idempotency-Key` e `X-Actor`, eventi nella stessa transazione; ciò che tocca capitale o sicurezza (modalità di approvazione, chiavi del broker) chiede `confirm:true`; il Risk Gate resta sovrano; nessuna distinzione paper/live nella UI.

## Fuori scope ora

Utenti multipli e permessi, deploy, modifica del codice o dei tool degli agenti, aggiunta di nuovi agenti dalla UI.
