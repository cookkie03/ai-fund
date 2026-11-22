# Brief: pagina Portafoglio del cockpit

Confermato da Luca il 2026-11-22. Terza pagina dopo Terminale e Ufficio, nel sistema Legend esistente (`DESIGN.md`).

## Per chi e perché

Luca gestisce il portafoglio come in un'app di banking desktop, **prima di tutto professionale nelle informazioni**, poi piacevole: la sensazione moderna di Revolut e Trade Republic, ma con la densità informativa di un gestore (IBKR Portfolio Analyst, Bloomberg PORT come asticella dei contenuti, non dell'aspetto). Lavora sugli stessi dati e con le stesse regole degli agenti; il Risk Gate resta sovrano.

## Struttura (scelta: panoramica + sezioni)

**Panoramica in alto, sempre visibile:**
- Equity, variazione oggi (assoluta e %), PnL non realizzato, PnL realizzato nel periodo, investito, cassa e riserva di cassa, numero di posizioni.
- Curva dell'equity con periodi (1G, 1S, 1M, 3M, YTD, 1A, Tutto) e benchmark SPY sovrapponibile; drawdown come area sotto.
- Allocazione per settore e per posizione, con la soglia di rischio visibile (es. 30% per settore).

**Sezioni a schede sotto la panoramica:**
1. **Posizioni**: ticker, quantità, prezzo medio, prezzo corrente, valore, peso %, PnL non realizzato (assoluto e %), stop e target attivi, rischio aperto fino allo stop (in $ e % dell'equity), settore, giorni in posizione, agente che ha proposto il trade. Azioni per riga: chiudi o riduci, modifica stop e target, chiedi a un agente.
2. **Operazioni**: ordini (in attesa di approvazione in cima, con Approva/Rifiuta come nel Terminale) e storico trade chiusi (entrata, uscita, motivo di uscita, PnL, R multiplo, durata, agente proponente).
3. **Performance**: rendimento per periodo, PnL realizzato e non realizzato, max drawdown e drawdown attuale, volatilità annualizzata, Sharpe, Sortino, win rate, profit factor, expectancy (in $ e in R), confronto con SPY (rendimento, beta, correlazione). **Attribuzione**: contributo al rendimento per posizione, per settore e per agente proponente.
4. **Rischio e vincoli**: ogni limite del Risk Gate con il suo utilizzo attuale (rischio per trade, peso massimo per posizione, esposizione per settore, numero di posizioni, riserva di cassa, R:R minimo, embargo trimestrali) e lo stato (entro, vicino, oltre). **Modificabili subito** con conferma esplicita; ogni modifica registra chi, quando, valori prima e dopo, motivo; storico delle modifiche visibile.

## Azioni (tutte passano dal Runtime e dal Risk Gate)

- **Approva / rifiuta ordini** in attesa (comandi esistenti `approve_order`, `reject_order` con `confirm:true`).
- **Chiudi o riduci una posizione**: totale o parziale, a mercato o limite, con anteprima (quantità, valore stimato, PnL che si realizza) e conferma.
- **Modifica stop e target** di una posizione aperta, con anteprima del nuovo rischio; allontanare lo stop aumenta il rischio e viene controllato dal Risk Gate, stringerlo è sempre consentito.
- **Chiedi a un agente**: da una posizione apre la chat di PM o Risk Analyst sul topic del ticker nell'Ufficio (riuso, nessun backend nuovo).
- **Modifica dei vincoli** di rischio, con conferma e motivo.

## Stati

Caricamento; portafoglio vuoto (nessuna posizione, solo cassa); storico troppo corto per metriche (dire quanti giorni servono, non mostrare Sharpe su 3 punti); benchmark non disponibile; broker disconnesso o snapshot vecchio (con età); Halt attivo (azioni di capitale disabilitate con motivo); comando rifiutato dal Risk Gate (mostra le regole violate); limite oltre soglia dopo una modifica dei vincoli (le posizioni esistenti non vengono chiuse: si segnala lo sforamento).

## Telefono (390 px)

Panoramica compatta (equity, oggi, curva), schede come selettore, posizioni come lista con dettaglio a foglio; azioni di capitale disponibili con la stessa conferma.

## Fuori scope

Evaluation completa degli agenti (oltre l'attribuzione), report fiscali, export, multi-valuta, opzioni e derivati, order book.
