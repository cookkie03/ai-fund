# 0004. Agenti del ticker e scheda del ticker

- **Stato**: Accettato
- **Data**: 2026-11-22
- **Autore**: Backend team

## Contesto

In precedenza il Portfolio Manager apriva direttamente un ciclo per ciascun ticker, coordinando gli specialisti nella chat del titolo. Questa struttura appesantiva il ruolo del PM e mancava di un documento persistente e strutturato da consultare prima delle decisioni.

## Decisione

1. **Agenti del ticker**: viene introdotto il ruolo `ticker:<SIMBOLO>` (`ticker_agent`) che coordina gli specialisti, aggiorna la scheda e sottopone una proposta al PM (`submit_proposal`) senza poter piazzare ordini.
2. **Portfolio Manager a livello di portafoglio**: confronta le proposte aperte (`read_proposals`), valuta cassa, posizioni e concentrazione, quindi decide con `decide_proposal` (`accept`, `defer`, `reject`, `ask`).
3. **Scheda del ticker (Dossier)**: `ticker_state` evolve in una scheda strutturata e versionata (`dossier_versions`), con autore, data di riferimento, confidenza e marcatura deterministica `stale`. I comandi `add_dossier_note` permettono all'utente di aggiungere pareri senior firmati e idempotenti.
4. **Risk Gate invariato**: `accept` avvia sempre la verifica deterministica del Risk Gate prima dell'inoltro al broker.

## Conseguenze

- Separazione netta tra proposta del ticker e allocazione complessiva di portafoglio.
- Storico delle versioni consultabile (`dossier_history`), con piena compatibilità per i client esistenti.
- Eventi dedicati per scheda e proposte (`dossier.updated`, `proposal.submitted`, `proposal.decided`).
