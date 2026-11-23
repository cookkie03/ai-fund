# Brief: agenti del ticker e scheda del ticker

Confermato da Luca il 2026-11-22.

## Da dove viene

Decisione di giugno 2026 nella wiki (`wiki/system/orchestration/parallelism-design.md`, "architettura a imbuto": screening → coda di priorità → deep-dive per ticker → scheda ticker nel DB) e idea "Agente Single Ticker" (`wiki/system/foundation/ideas-log.md`). La spec MVP di novembre (`.scratch/agent-mvp/spec.md`) l'aveva rimandata: oggi un solo PM apre un Ciclo di analisi per ticker, con una chat per ticker e fino a 3 cicli in parallelo; `subagent` è solo un aiutante generico in sola lettura. Lo stato per ticker esiste in forma parziale (`ticker_state`: analisi per agente, suggerimenti, coefficienti, bozza, decisione).

## Decisioni

1. **Due livelli di gestione.** Il **Portfolio Manager** lavora sul portafoglio: confronta le proposte di tutti i ticker con posizioni, cassa, esposizione e vincoli, e decide (accetta, rimanda, ridimensiona, chiede altro). L'**Agente del ticker** lavora su un solo titolo: orchestra gli specialist (Market, Sentiment, Technical, Fundamental, Risk) nella chat del ticker, scrive tesi, coefficienti e proposta nella scheda, e la sottopone al PM. **Il ticker propone, il PM decide**; poi Bozza deterministica, Risk Gate sovrano, coda di approvazione.
2. **Agente del ticker persistente.** Un'identità per ogni ticker in portafoglio o in analisi (es. "Agente NVDA"), con la sua chat e la sua memoria nella scheda; si attiva a ogni ciclo e resta inattivo tra un ciclo e l'altro. Un'unica configurazione di modello per tutti gli agenti del ticker.
3. **Scheda del ticker (investment state).** Documento sempre aggiornato per ticker a cui fanno riferimento tutti gli agenti: identità e contesto del titolo, contesto di portafoglio, analisi di ogni specialist, tesi (pro e contro, direzione, conviction, catalizzatori, prossima verifica), proposta operativa, verdetto di rischio, storico delle decisioni, lezioni dai trade passati, note di Luca. Ogni fatto ha autore, data, data di riferimento, confidenza e stato (attivo, vecchio, superato): la scheda è una base, non un oracolo. Campi dal template della wiki `wiki/system/investment/investment-state-template.md` (prima i CORE).
4. **In UI: pagina `/ticker/:symbol`.** Dossier del ticker raggiungibile da ovunque (Terminale, Portafoglio, Ufficio, Notizie). L'Ufficio viene riprogettato per mostrare la struttura a due livelli: squadra centrale (PM e specialist) e desk degli agenti del ticker, con le proposte in attesa del PM.

## Fuori scope ora

Screening deterministico dell'universo e coda di priorità automatica (strati successivi dell'imbuto, agganci da prevedere), workspace per ticker con file e git, RAG sulle esperienze.
