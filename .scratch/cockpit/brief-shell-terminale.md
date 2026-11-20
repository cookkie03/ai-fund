# Brief Impeccable: shell + Terminale (confermato da Luca il 2026-11-20)

Mode: **Operate**. Build path: **code-led**. Direzione visiva: **standard di categoria** eseguito al livello dei migliori prodotti, senza metafore (scelta di Luca dopo due giri di direzioni; seed della prima mano `seed:f38469220b10fc8f`, canon scelto al secondo giro). Contesto completo: `PRODUCT.md`, `docs/frontend.md`, `docs/dashboard.md` (API del Runtime).

## Job e pubblico

Luca, unico proprietario, entra nell'ufficio autonomo come **collega jolly** da desktop o telefono. Il motore non lo aspetta: lui osserva, indirizza e lavora sullo stesso materiale degli agenti. Il Terminale è la pagina tecnica: il grafico è l'ambiente principale del Technical Analyst, condiviso con Luca.

## Riferimenti di qualità

TradingView e Interactive Brokers TWS per il Terminale; app di Claude, Linear e Slack per pannelli agenti e Bridge. Componenti moderni e belli da applicazione professionale, tema scuro unico, numeri tabulari.

## Shell (comune alle sei pagine)

- Barra laterale: Assistente, Ufficio, Terminale, Notizie, Portafoglio, Configurazioni; Inbox con contatore.
- Barra in alto: account attivo e selettore (un Runtime per account), stato Runtime e stream broker con età dei dati, orario di mercato, equity e P&L del giorno, Halt.
- Pannello laterale apribile da ogni pagina con il **Bridge** (solo UI per ora: l'agente si implementa dopo nel Runtime) e campo per scrivere a un agente con `@agente`.
- Halt attivo e Runtime irraggiungibile cambiano visibilmente tutta la shell.

## Terminale

- **Sinistra, watchlist condivisa**: prezzo, variazione, mini-grafico; ogni riga dice chi l'ha aggiunta (Luca o agente), quando e con quale nota. Aggiungi, togli, annota con gli stessi comandi degli agenti (`add_watchlist`, `remove_watchlist`).
- **Centro, grafico**: candele e volumi, indicatori (es. EMA, RSI, ATR) in pannelli; sopra il grafico livelli e linee degli agenti firmati dall'autore, disegni di Luca che gli agenti leggono, entry/TP/SL/trailing dei trade aperti. Timeframe di default 1h (`bar_timeframe`). Libreria: vedi `.scratch/cockpit/chart-library.md` (ricerca in corso).
- **Destra, attività sullo strumento** (idea iniziale, da verificare in build: Luca dubita che sia coerente): agenti che ci lavorano, ultimo ciclo, tesi corrente e coefficienti da `ticker_state`; messaggio a un agente su quel ticker.
- **Sotto, ordini**: tab Aperti, Pendenti, Eseguiti, Trade; pendenti approvabili/rifiutabili con conferma (`approve_order` con `confirm: true`, `reject_order`) negli account in manuale, con esito del Risk Gate.
- Niente order book.

## Stati

Caricamento (skeleton), watchlist vuota, ticker senza dati, dati vecchi (SSE disconnesso, età visibile), rifiuto del Risk Gate o del dominio (`ok: false` con ragioni), Halt, Runtime irraggiungibile. Mai dati finti in produzione; i dati di sviluppo vengono da `build_test_office` + `Runtime` (vedi `docs/dashboard.md` §3.1).

## Responsive

Telefono (390 px): grafico per primo, poi watchlist, attività e ordini come schede. Tutto usabile da tastiera.

## Backend necessario prima della build (nel Runtime)

- Lettura OHLCV (e indicatori, se la libreria scelta non li calcola lato client), gli stessi dati che usano gli agenti.
- Annotazioni del grafico: tabella, lettura e scrittura per il frontend con firma dell'autore, evento SSE a ogni modifica. I tool degli agenti sulle annotazioni vengono dopo.
- Collegamento browser: proxy Vite verso il Runtime (niente CORS), stream SSE senza header Authorization in loopback.

## Fuori scope

Bridge funzionante, order book, altre pagine oltre shell e Terminale, toolset del Technical sul grafico (prossime versioni).

## Chiusura (regola Impeccable)

Unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
