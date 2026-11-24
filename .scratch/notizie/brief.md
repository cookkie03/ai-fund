# Brief: pagina Notizie

Decisioni di Luca del 2026-11-24, che completano quella del 2026-11-20 (wiki `system/interface/frontend-module.md`: «Notizie: l'ambiente news degli agenti, con gli stessi tool: Luca legge, filtra, seleziona e invia notizie agli agenti»). Branch della pagina: **`notizie-frontend`** (backend e frontend insieme, PR verso `main` con CI verde).

## Cosa è

`/notizie` è lo stesso ambiente notizie che usano gli agenti, aperto a Luca come collega: le stesse fonti, salvate nel DB del Runtime, lette dagli agenti con i loro tool e da Luca nella pagina. Luca legge, filtra, vede quali agenti hanno usato una notizia e la inoltra a chi deve pesarla.

## Decisioni

1. **Fonti: tutte.** Alpaca (come oggi), **feed RSS** che Luca aggiunge e toglie, **OpenBB** (notizie per società e mondo), **calendario macro ed earnings** (CPI, FOMC, trimestrali). Una sola ingestione nel Runtime per agenti e pagina; ogni notizia porta fonte e provider.
2. **Invio: inoltro con nota.** Luca sceglie un agente o un ticker (va all'agente del ticker `ticker:<SYM>`), aggiunge una nota sua; la notizia arriva nella chat del destinatario come parere da pesare, non come ordine.
3. **Layout: flusso + lettore + uso.** Flusso filtrabile (ticker, tema, fonte, provider, portafoglio/watchlist, ricerca), lettore a destra, e per ogni notizia la traccia d'uso: quali agenti l'hanno letta, citata o ricevuta, con link al ciclo e alla chat. Calendario macro/earnings accanto al flusso.
4. **Nessuna sintesi LLM nella pagina.** Solo lettura; per un riassunto Luca chiede al Bridge. Etichette di ticker deterministiche, niente costi LLM continui.

## Regole che non cambiano

Runtime unico writer, comandi con `Idempotency-Key` e `X-Actor`, eventi nella stessa transazione; le notizie sono osservazioni, non punteggi; il parere di Luca è un'opinione che gli agenti pesano; nessuna distinzione paper/live.

## Fuori scope ora

Sintesi o punteggi di sentiment automatici, social (X, Reddit), notifiche push, paywall e scraping del testo integrale oltre quanto la fonte fornisce.
