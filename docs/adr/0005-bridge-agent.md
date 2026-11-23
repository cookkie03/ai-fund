# 0005. Bridge Agent e briefing del Cockpit

- **Stato**: Accettato
- **Data**: 2026-11-23
- **Autore**: Backend team

## Contesto

L'Ufficio di Trading è un motore autonomo al 100%, governato dal Risk Gate. Con l'evoluzione del cockpit verso uno spazio di lavoro collaborativo in cui Luca è un membro dell'ufficio alla pari degli agenti, serviva un interlocutore centrale capace di dialogare in linguaggio naturale, interrogare lo stato di tutto l'ufficio, relazionarsi con gli agenti specialisti e predisporre interventi operativi richiesti da Luca.

Inizialmente ipotizzato come "Configuration & State Agent" post-MVP, la decisione del 2026-11-20 e le specifiche dell'Assistente ne hanno anticipato la costruzione all'interno del Runtime principale.

## Decisione

1. **Agente `bridge` nativo nel Runtime**:
   - Viene introdotto l'agente `bridge` (`kind: "core"`, `supervisor: null`) configurato in `config/office.toml` e `config/office_settings.py` con prompt dedicato in italiano (`prompts/bridge.md`).
   - I turni girano nel thread worker asincrono del Runtime (mai nel thread HTTP), con budget di passi per turno, blocco delle chiamate concorrenti per conversazione e limite di costo giornaliero (`daily_budget`).
   - Comandi dedicati per Luca: `bridge_say`, `bridge_rename_conversation`, `bridge_archive_conversation`, `bridge_stop`, `bridge_action_decide`.

2. **Accesso completo in lettura e sintesi compatta**:
   - Il Bridge dispone di tool di lettura su portafoglio, posizioni, ordini, trade, limiti di rischio, schede (dossier), proposte, chat degli agenti, chiamate ai tool, costi/token, watchlist, annotazioni, dati di mercato (OHLCV, indicatori), inbox, eventi e briefing.
   - I risultati restituiti al modello sono sintetici e compatti per favorire risposte dense e leggibili.

3. **Canale bidirezionale verso gli agenti (`message_agent`)**:
   - Il Bridge può scrivere a qualunque agente (`message_agent`) con prefisso `[Per conto di Luca]`.
   - Se l'agente risponde in quella chat, la risposta viene catturata deterministicamente e inserita nella conversazione del Bridge con `kind: "agent_relay"`, avviando un turno di sintesi per Luca.
   - Un messaggio destinato al Portfolio Manager genera contestualmente uno Scheduled task sul ticker, preservando le invarianti di attivazione.

4. **Separazione rigida tra azioni senza capitale e azioni con capitale**:
   - **Azioni senza capitale** (`add_watchlist`, `remove_watchlist`, `add_dossier_note`, `enqueue_task`, `refresh_data`, `upsert_annotation`, `strike_annotation`, `mark_inbox_read`): eseguite immediatamente dal Bridge con attore `bridge`.
   - **Azioni con capitale** (`approve_order`, `reject_order`, `close_position`, `modify_exit`, `decide_proposal`, `halt`, `resume`, `update_risk_limits`): **nessun tool di esecuzione diretta esiste nel registro dell'agente**. Il Bridge può unicamente invocare `propose_action`, che valida il payload con il modello Pydantic del comando, esegue il `dry_run`/preview e salva l'azione con stato `pending`.

5. **Esecuzione dallo stesso handler con conferma di Luca**:
   - L'azione in attesa viene eseguita solo se Luca invia `bridge_action_decide` con `decision: "confirm"` e `confirm: true`.
   - L'esecuzione riutilizza **lo stesso identico handler** del comando originario con attore `luca`, rieseguendo tutti i controlli real-time: stato attuale della posizione/ordine, controlli di Halt, e soprattutto la verifica del **Risk Gate sovrano**.
   - Se le condizioni di mercato o lo stato sono mutati, l'azione fallisce con motivazione chiara e l'esito viene commentato dal Bridge nella conversazione.

6. **Briefing deterministico e aggiornato**:
   - Endpoint `GET /v1/read/briefing?since=` che raccoglie in modo deterministico trade, ordini pendenti, proposte, alert, eventi Halt/Resume, aggiornamenti dossier, errori e cambi ai limiti di rischio da `since` (default: ultima lettura `mark_briefing_seen`, altrimenti 24h).
   - Sintesi `summary_text` scritta dal Bridge, memorizzata in cache e invalidata dai nuovi eventi.

## Conseguenze

- **Sicurezza finanziaria assoluta**: nessun comando che muove capitale o modifica vincoli di rischio può essere eseguito senza l'azione esplicita e deliberata di Luca nella UI.
- **Coerenza logica e zero codice duplicato**: la validazione e l'esecuzione passano per gli stessi handler del Runtime usati dalla CLI e dalla UI.
- **Osservabilità SSE completa**: flusso di eventi dal vivo arricchito con `bridge.conversation`, `bridge.message`, `bridge.status`, `bridge.action`, `briefing.updated`, oltre a `tool.started` e `tool.finished` per tutti gli agenti.
