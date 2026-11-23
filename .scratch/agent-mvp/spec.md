---
title: Spec — MVP dell'ufficio di agenti di trading
status: ready-for-agent
created: 2026-11-18
sources:
  - GLOSSARY.md
  - docs/adr/0001-risk-a-due-livelli.md
  - docs/adr/0002-nostro-codice-non-fork-openalice.md
  - ../trading-agent-wiki/wiki/system/foundation/decision-log.md (righe 2026-11-18)
  - ../trading-agent-wiki/wiki/system/agents/agent-tools.md
---

# Spec — MVP dell'ufficio di agenti di trading

## Problem Statement

Luca vuole un sistema che analizzi azioni USA e operi in autonomia su un conto broker, con un gruppo di agenti specializzati che ragionano come colleghi in un unico ufficio. Il prototipo attuale chiama gli Analyst una sola volta in sequenza, usa regole fisse al posto di LLM, non ha chat né messaggi, non ha una memoria delle decisioni e lascia ordini e rischio a pezzi sparsi. Non c'è un modo unico per richiamare gli agenti, né un registro completo di ciò che fanno, né una CLI per seguire e governare il sistema. Le tabelle del DB sono cresciute a caso e i dati finanziari non hanno un'organizzazione né una politica di conservazione.

## Solution

Un motore Python, eseguibile da CLI in sviluppo e in Docker sul mini-server di casa, che fa lavorare sei Agenti pari (Market, Sentiment, Technical, Fundamental, Risk Analyst e Portfolio Manager) attraverso messaggi nelle loro Chat. Ogni agente viene richiamato solo da uno Scheduled task. Il PM apre un Ciclo di analisi su un ticker, orchestra gli Analyst, e decide: accettare l'ordine, rimandare o chiedere altro. Gli Analyst scrivono Analysis e coefficienti nello state; una Bozza dell'ordine deterministica traduce i coefficienti in un Bracket order; il Risk Gate verifica i limiti rigidi; la Coda di approvazione (per ora in modalità automatica) lo invia al broker. Ogni Trade è seguito fino all'uscita, con trailing stop deterministico. Tutto ciò che accade (messaggi, chiamate LLM e tool, token e costi, ordini, comandi) viene registrato nel DB; i dati finanziari vivono nel DB come cache organizzata per tipo, con downsampling. Una CLI `trading-agent` permette a Luca di avviare, osservare, scrivere agli agenti, approvare ordini e fermare tutto.

## User Stories

### Avvio, configurazione, deploy

1. Come Luca, voglio avviare il motore con un comando CLI, così che scheduler e agenti lavorino in continuo.
2. Come Luca, voglio avviare lo stesso motore in un container Docker sul mini-server, così che giri 24/7 senza il mio portatile.
3. Come Luca, voglio tenere chiavi ed endpoint di LLM e broker in `.env`, così che i segreti non finiscano nel codice né nel DB.
4. Come Luca, voglio tenere le impostazioni (modelli, sforzo, limiti, orari, budget, conservazione) in un file di impostazioni dedicato, così da cambiarle senza toccare il codice.
5. Come Luca, voglio un comando che verifichi la configurazione, così da scoprire subito chiavi mancanti o valori fuori limite.
6. Come Luca, voglio scegliere per ogni agente endpoint compatibile OpenAI e modello, così da usare provider diversi per ruoli diversi.
7. Come Luca, voglio impostare per ogni agente lo sforzo di ragionamento (basso, medio, alto), così da bilanciare qualità e costo.
8. Come Luca, voglio cambiare le credenziali del broker come cambio quelle degli LLM, così da passare da paper a live senza modifiche al codice.
9. Come Agente, non voglio sapere se il broker è paper o live, così da non avere bias nelle decisioni.
10. Come Luca, voglio che dati e DB persistano fuori dal container, così da non perdere nulla a un riavvio.

### Scheduled task e Trigger engine

11. Come Agente, voglio essere richiamato solo da uno Scheduled task, così che ogni attivazione abbia una causa chiara.
12. Come Trigger engine, voglio trasformare ogni Alert esterno (prezzo, calendario, trimestrale) in uno Scheduled task immediato, così che tutte le fonti seguano lo stesso percorso.
13. Come Trigger engine, voglio un traduttore deterministico per ogni fonte, che dallo Scheduled task produca il prompt di apertura, così che il PM riceva sempre un contesto uniforme.
14. Come PM, voglio programmare uno Scheduled task futuro su un ticker con una nota su cosa verificare, così da tornare sul titolo al momento giusto.
15. Come Market Analyst, voglio programmarmi Scheduled task sui miei temi, così da seguire i catalizzatori in autonomia.
16. Come Market Analyst, voglio una base di attivazioni fisse (pre-market ed eventi macro del calendario), così da non dipendere solo dai miei task.
17. Come sistema, voglio che uno Scheduled task su un ticker già in analisi entri come messaggio nel ciclo aperto, così da non aprire cicli doppi.
18. Come sistema, voglio che due Scheduled task in coda sulla stessa chat si fondano in uno composto, così da non ripetere il lavoro.
19. Come sistema, voglio che la data di uno Scheduled task programmato da un agente sia limitata tra un minimo e un massimo configurabili in giorni di borsa, così da evitare controlli assurdi.
20. Come sistema, voglio consegnare gli Scheduled task scaduti anche dopo un riavvio, senza riprovare a raffica quelli falliti, così da non perdere né duplicare lavoro.
21. Come Luca, voglio creare uno Scheduled task manuale su un ticker dalla CLI, così da far analizzare un titolo quando voglio.

### Ciclo di analisi e messaggi

22. Come PM, voglio aprire un Ciclo di analisi quando ricevo uno Scheduled task su un ticker, così da avviare l'analisi.
23. Come PM, voglio inviare un messaggio di apertura a Sentiment, Technical, Fundamental e Risk Analyst, così che tutti partano insieme.
24. Come PM, voglio ricevere in automatico l'ultima visione di mercato del settore del ticker, così da avere il contesto macro senza chiederlo.
25. Come Agente, voglio scrivere a qualsiasi altro agente con un messaggio che compare nella sua chat su quel ticker o tema, così da collaborare alla pari.
26. Come Agente, voglio che una richiesta al Market Analyst su un ticker venga recapitata nella chat del settore del ticker, così che arrivi al tema giusto.
27. Come Agente, voglio avere una chat separata per ogni ticker o tema, così da non mescolare argomenti.
28. Come Agente, voglio che a ogni nuovo ciclo la mia chat sia compattata con i timestamp di fine ciclo precedente e attuale, così da avere contesto senza esplodere i token.
29. Come sistema, voglio archiviare sempre i messaggi originali anche dopo la compattazione, così da poter ricostruire tutto.
30. Come sistema, voglio un Budget del ciclo generoso su messaggi e chiamate a subagent di tutti gli agenti, così da fermare i loop.
31. Come sistema, voglio che al raggiungimento del budget scatti un Rimando deterministico con avviso nell'Inbox, così che un loop non resti appeso.
32. Come Agente, voglio chiamare un subagent generico in sola lettura per un compito circoscritto, così da delegare ricerche senza sporcare la mia chat.
33. Come sistema, voglio che i subagent non possano scrivere ad altri agenti né creare ordini, così che restino aiutanti.
34. Come sistema, voglio far girare più Cicli di analisi in parallelo fino a un massimo configurabile, così da coprire più ticker insieme.
35. Come Luca, voglio scrivere in qualsiasi chat di qualsiasi agente dalla CLI, così da dare indicazioni; un mio messaggio al PM vale come Scheduled task manuale.

### State, Analysis e coefficienti

36. Come Analyst, voglio compilare la mia sezione testuale dello state del ticker, così che la mia Analysis resti strutturata e leggibile dagli altri.
37. Come Analyst, voglio suggerire direzione (buy, sell, hold) e convinzione (0–1), così che il PM possa aggregarle.
38. Come Risk Analyst, voglio impostare `k_entry` e la percentuale di rischio, così da influenzare entrata e size senza scrivere prezzi.
39. Come Technical Analyst, voglio impostare `k_stop`, `k_tp` e i coefficienti del trailing, così da adattare uscite e protezioni alla volatilità.
40. Come sistema, voglio rifiutare suggerimenti su campi non di competenza dell'agente o fuori limite, così che lo state resti coerente.
41. Come Agente, voglio leggere lo state del ticker con le Analysis degli altri, così da rispondere nel merito.
42. Come Risk Analyst, voglio portare la tesi contraria, così che il PM decida dopo un contraddittorio.

### Bozza dell'ordine e decisione

43. Come sistema, voglio calcolare la Bozza dell'ordine appena lo state ha gli input minimi, così che il PM abbia sempre un ordine concreto da valutare.
44. Come sistema, voglio ricalcolare la bozza a ogni cambio di coefficienti, così che i numeri siano sempre coerenti.
45. Come PM, voglio leggere la bozza corrente con entrata, SL, TP, size e R:R, così da decidere.
46. Come PM, voglio accettare l'ordine (buy, o sell su una posizione aperta) indicando la motivazione, così da operare.
47. Come PM, voglio rimandare con motivazione, così da non decidere quando il quadro non basta.
48. Come PM, voglio continuare il ciclo scrivendo agli agenti, così da chiedere ciò che manca.
49. Come sistema, voglio che ogni decisione del PM sia accompagnata da uno Scheduled task futuro sul ticker, così che nessun titolo resti dimenticato.
50. Come sistema, voglio che non esistano short: un sell è ammesso solo su una posizione aperta, così da rispettare lo scope.
51. Come PM, voglio leggere e modificare la watchlist, così da decidere quali titoli seguire.
52. Come PM, voglio ricevere a inizio ciclo l'esito deterministico della decisione precedente sul ticker e scriverci una lezione di una riga, così da imparare dagli errori.

### Risk Gate, approvazione, esecuzione

53. Come sistema, voglio che il Risk Gate controlli ogni ordine accettato contro i limiti rigidi, così che nessun ordine fuori regola parta.
54. Come sistema, voglio che il Risk Gate possa solo bloccare, mai modificare o approvare, così da restare un controllo puro.
55. Come sistema, voglio che un blocco del Risk Gate diventi un Rimando con la motivazione nella chat del PM e uno Scheduled task al giorno di borsa successivo, così che il PM sappia perché.
56. Come Luca, voglio una Coda di approvazione degli ordini dopo il Risk Gate, così da poter approvare a mano quando vorrò.
57. Come Luca, voglio un'impostazione che salti l'approvazione e invii subito, attiva per ora sul paper, così da vedere se il sistema funziona da solo.
58. Come Luca, quando l'approvazione è manuale voglio approvare o rifiutare un ordine dalla CLI, così da governare l'esecuzione.
59. Come sistema, voglio legare l'approvazione all'hash della bozza e farla decadere se la bozza cambia, così da non approvare ordini diversi da quelli visti.
60. Come sistema, voglio rieseguire il Risk Gate al momento dell'approvazione sul portafoglio aggiornato, così da non violare limiti nel frattempo.
61. Come sistema, voglio che un ordine non approvato entro fine seduta scada come Rimando, così che la coda non si riempia di ordini vecchi.
62. Come sistema, voglio che un mio rifiuto diventi un Rimando con la motivazione nella chat del PM, così che il PM ne tenga conto.
63. Come sistema, voglio inviare solo Bracket order con entrata limite, TP e SL, mai ordini a mercato, così da controllare prezzo e rischio.
64. Come sistema, voglio che l'ordine di entrata scada allo Scheduled task successivo sul ticker se non eseguito, così che non resti aperto all'infinito.
65. Come sistema, voglio inviare gli ordini solo a mercato aperto, altrimenti tenerli fino all'apertura, così da rispettare gli orari.
66. Come sistema, voglio serializzare Risk Gate, approvazione e invio anche con cicli paralleli, così che due ordini non consumino la stessa cassa.
67. Come sistema, voglio inviare ordini idempotenti con un identificativo client e riconciliarli col broker, così da non duplicare ordini dopo errori o riavvii.
68. Come PM, voglio vendere una posizione aperta con la stessa formula ATR a specchio dell'acquisto, così che anche l'uscita sia a prezzo limite controllato.
69. Come sistema, voglio attuare la vendita spostando il TP del bracket aperto al prezzo di vendita e lasciando lo SL, così da non lasciare la posizione scoperta.

### Trade e trailing stop

70. Come sistema, voglio registrare ogni Trade dall'entrata all'uscita con tutti gli eventi, così da sapere esattamente cosa è successo.
71. Come sistema, voglio registrare se un Trade esce per TP, SL, vendita del PM o scadenza, con prezzi e orari, così da valutare le decisioni.
72. Come sistema, voglio attivare il trailing stop quando il prezzo supera la soglia `entry + k_trail_act·ATR`, così da proteggere il guadagno.
73. Come sistema, all'attivazione voglio spostare lo stop a pareggio e poi seguire il massimo a `max − k_trail·ATR` senza mai abbassarlo, così da lasciar correre il profitto.
74. Come sistema, voglio che il trailing modifichi l'ordine al broker senza passare dagli LLM, così da essere rapido e deterministico.
75. Come Luca, voglio vedere i Trade aperti e chiusi dalla CLI, così da seguire il portafoglio.

### Market Analyst

76. Come Market Analyst, voglio lavorare fuori dai Cicli di analisi sulle mie chat di tema, così da seguire macro e settori con continuità.
77. Come Market Analyst, voglio aggiornare nello state una visione di mercato per ogni settore, così che i cicli la ricevano.
78. Come Market Analyst, voglio scrivere al PM quando un catalizzatore tocca titoli in portafoglio o watchlist, così che si apra un ciclo per ogni ticker toccato.
79. Come Market Analyst, voglio rispondere alle richieste degli altri agenti, così da essere un collega disponibile.
80. Come sistema, voglio che ogni attivazione del Market Analyst abbia un proprio budget, così da fermarne i loop.

### Tool degli Analyst

81. Come Market Analyst, voglio serie macro, news per tema, calendario economico e performance settoriali, così da analizzare i catalizzatori.
82. Come Sentiment Analyst, voglio news per ticker, rating degli analisti e transazioni insider, così da giudicare umore e posizionamento.
83. Come Technical Analyst, voglio quotazione, storico OHLCV e indicatori (SMA, EMA, RSI, MACD, ATR, pivot), così da leggere il grafico.
84. Come Fundamental Analyst, voglio bilanci, indicatori di bilancio e date e sorprese delle trimestrali, così da valutare l'azienda e il rischio evento.
85. Come Risk Analyst, voglio il rischio del portafoglio (esposizioni, concentrazione, rischio aperto, correlazione) e la bozza corrente, così da scegliere i coefficienti.
86. Come Agente, voglio leggere il portafoglio (cassa, equity, posizioni, ordini aperti), così da ragionare sul contesto reale.
87. Come sistema, voglio che nessun tool di agente invii ordini al broker, così che l'esecuzione resti nel codice deterministico.

### Dati finanziari

88. Come tool, voglio leggere i dati dal DB e scaricarli via OpenBB o Alpaca solo se mancano o sono scaduti, così da risparmiare chiamate e tempo.
89. Come sistema, voglio aggiornare in anticipo i dati di watchlist e portafoglio (OHLCV dopo la chiusura, calendario e news ogni giorno, fondamentali e rating ogni settimana, macro secondo frequenza), così che i cicli trovino dati pronti.
90. Come sistema, voglio organizzare i dati finanziari in tabelle per tipo con fonte e data di download, così che restino ordinati e tracciabili.
91. Come sistema, voglio una chiave unica per ogni dato, così da non salvare duplicati.
92. Come sistema, voglio un'anagrafica dei titoli con settore e industria, così da recapitare le richieste al tema giusto e calcolare le esposizioni.
93. Come sistema, voglio calcolare gli indicatori al momento dalle barre invece di salvarli, così da non duplicare dati.
94. Come sistema, voglio marcare come vecchio un dato che non si è potuto aggiornare, senza nasconderlo, così che gli agenti sappiano quanto fidarsi.
95. Come Luca, voglio un comando di refresh dei dati per il debug, così da forzare un aggiornamento.

### Conservazione e downsampling

96. Come sistema, voglio tenere i prezzi giornalieri per 5 anni, settimanali tra 5 e 10 anni, mensili oltre, così che lo storico non esploda.
97. Come sistema, voglio tenere le barre orarie 90 giorni e poi ridurle a giornaliere, così da contenere lo spazio.
98. Come sistema, voglio tenere il testo completo delle news 90 giorni e poi solo titolo e sintesi, così da risparmiare spazio.
99. Come sistema, voglio tenere prompt e risposte LLM completi 180 giorni e poi solo i metadati, così da risparmiare spazio senza perdere i conti.
100. Come sistema, voglio tenere per sempre chat, decisioni, ordini, Trade ed eventi, compressi, così da non perdere la storia.
101. Come sistema, voglio un job settimanale che applichi la conservazione e liberi lo spazio, così che il DB resti piccolo.
102. Come Luca, voglio un avviso quando il DB supera una soglia configurabile, così da intervenire in tempo.

### Registro completo su DB

103. Come Luca, voglio che il DB registri agenti con configurazione e versione del prompt, così da sapere chi ha prodotto cosa.
104. Come Luca, voglio che il DB registri chat e messaggi con autore, orario e testo, così da rileggere ogni conversazione.
105. Come Luca, voglio che il DB registri ogni chiamata LLM con agente, chat, token, costo, durata, prompt e risposta compressi, così da controllare costi e qualità.
106. Come Luca, voglio che il DB registri ogni chiamata a tool con parametri, risultato ed errori, così da capire su quali dati gli agenti hanno deciso.
107. Come Luca, voglio che il DB registri Scheduled task, decisioni, ordini, eventi dei Trade e miei comandi CLI, così da avere una traccia completa.
108. Come sistema, voglio scrivere il registro a blocchi senza mai fermare gli agenti, così che il log non rallenti il lavoro.
109. Come sistema, voglio salvare una sola volta i testi ripetuti (system prompt), così da non sprecare spazio.
110. Come Agente, non voglio vedere token e costi, così da non esserne influenzato.

### Errori, sicurezza, Inbox

111. Come sistema, voglio riprovare 2 volte con attesa crescente una chiamata LLM o tool fallita, così da superare errori temporanei.
112. Come Agente, se l'errore persiste voglio scriverlo nella mia chat e lasciar proseguire il ciclo, così che un guasto non blocchi tutto.
113. Come sistema, se fallisce il PM voglio un Rimando deterministico con avviso, così che il ciclo si chiuda comunque.
114. Come Luca, voglio un comando di arresto (halt) che fermi il Trigger engine e blocchi nuovi ordini, con un'opzione per cancellare quelli aperti, così da fermare tutto in emergenza.
115. Come Luca, voglio un comando per riprendere (resume), così da ripartire dopo un arresto.
116. Come sistema, voglio che il Risk Gate verifichi l'arresto prima di ogni invio, così che nessun ordine sfugga.
117. Come Luca, voglio un'Inbox con budget esauriti, blocchi del Risk Gate, errori ripetuti, ordini eseguiti o scaduti, arresti e DB troppo grande, così da sapere cosa richiede attenzione.
118. Come Luca, voglio leggere l'Inbox dalla CLI, così da non dover scavare nei log.

### CLI e osservazione

119. Come Luca, voglio elencare i cicli e vedere il dettaglio di uno, così da seguire il lavoro.
120. Come Luca, voglio leggere una chat di un agente, così da vedere come ragiona.
121. Come Luca, voglio vedere lo state di un ticker, così da capire bozza e Analysis.
122. Come Luca, voglio vedere e modificare la watchlist dalla CLI, così da intervenire sui titoli seguiti.
123. Come Luca, voglio elencare gli ordini e i Trade, così da controllare l'esecuzione.
124. Come Luca, voglio sincronizzare il portafoglio dal broker, così da allineare posizioni e cassa.

### Prompt

125. Come Luca, voglio un system prompt in Markdown per ogni agente, versionato nel repository, così da poterlo rivedere e migliorare.
126. Come sistema, voglio registrare l'hash del prompt usato in ogni chiamata LLM, così da sapere quale versione ha prodotto ogni decisione.

## Implementation Decisions

**Struttura.** Monolite modulare nell'alberatura approvata (brokers, data, storage, analysis, tools, agents, workflows, execution, interface, config, bootstrap). Il codice agenti attuale si riscrive (autorizzazione di Luca): si riusano gli indicatori, il contratto broker con l'adapter Alpaca e il contratto bracket, la base di sizing e limiti del modulo rischio, gli adapter dati OpenBB e Alpaca, il calendario di mercato. Le regole fisse degli Analyst attuali e gli adapter relativi diventano fake per i test. Il modulo PM via OmniRoute si elimina. Le tabelle attuali del prototipo si sostituiscono con lo schema qui sotto.

**Moduli profondi e interfacce.**
- *Motore (Office)*: interfaccia minima `deliver(scheduled_task)` e `run()` (loop dello scheduler). Dentro: Trigger engine, coda degli Scheduled task con fusione, apertura e chiusura dei cicli, budget, parallelismo, compattazione delle chat. È il punto di test principale.
- *Backend agente*: interfaccia sostituibile `step(agent, chat_context, tools) → messaggi e chiamate a tool`. Implementazione MVP con LangGraph su endpoint compatibile OpenAI; implementazione finta a copione per i test. Pronto per backend futuri (Claude Code, Pi) via MCP.
- *Ambiente degli agenti*: lo strato di tool, state, chat e ordini, separato dal runtime, con schemi Pydantic per gli input e output dei tool.
- *Fornitore dati di mercato*: contratto interno con adapter OpenBB (provider di default yfinance, FRED) e Alpaca (quotazioni, news, portafoglio); il layer di cache DB-first sta sopra il contratto.
- *Broker*: contratto esistente esteso con invio, modifica e cancellazione di bracket, identificativo client, riconciliazione; adapter Alpaca. Nessuna informazione paper/live esposta agli agenti.
- *Calcoli deterministici* come funzioni pure: Bozza dell'ordine, Risk Gate (lista ordinata di guard, ispirata a OpenAlice), trailing stop, traduttori degli Scheduled task, downsampling, limiti della data degli Scheduled task, fusione degli Scheduled task.
- *Registro*: scrittore asincrono a blocchi verso il DB.
- *CLI*: `trading-agent` con i comandi run, task (crea Scheduled task manuale), say (scrivi in una chat), cycles list/show, chat show, state show, watchlist, orders list/approve/reject, trades list, portfolio sync, data refresh, inbox, halt/resume, config check.

**Bozza dell'ordine** (impianto ATR approvato il 2026-06-04):

```
entry = current_price − k_entry·ATR          (acquisto)
entry = current_price + k_entry·ATR          (vendita di una posizione aperta)
SL    = entry − k_stop·ATR
TP    = entry + k_tp·ATR
size  = floor(equity × risk_fraction / (entry − SL))
trailing: attivo da entry + k_trail_act·ATR; stop → entry, poi max − k_trail·ATR, mai verso il basso
```

Default: ATR(14), `k_stop` 2, `k_tp` 3, `k_trail_act` 1,5, `k_trail` 1; `k_entry` decresce al crescere della convinzione. Responsabilità: Risk Analyst `k_entry` e `risk_fraction`; Technical Analyst `k_stop`, `k_tp`, `k_trail_act`, `k_trail`. Gli agenti scelgono coefficienti, mai prezzi.

**Limiti di default del Risk Gate** (configurabili): rischio per trade ≤ 1% dell'equity; posizione ≤ 10%; settore ≤ 30%; massimo 30 posizioni aperte; riserva di cassa ≥ 5%; R:R ≥ 1,5; nessuna nuova entrata entro 2 giorni di borsa da una trimestrale; arresto attivo blocca tutto.

**Decisione del PM e Agenti del ticker.** (Aggiornamento 2026-11-22, ADR 0004): architettura a due livelli. L'Agente del ticker (`ticker:<SYM>`) orchestra gli Analyst sul titolo, scrive tesi e coefficienti nella Scheda del ticker (dossier versionato) e sottopone una proposta (`submit_proposal`) al PM senza poter creare ordini. Il Portfolio Manager confronta le proposte con il portafoglio e delibera con `decide_proposal`: `accept` (con eventuale ridimensionamento), `defer` (con data di verifica futura obbligatoria), `reject` o `ask` (domande all'agente del ticker). Solo `accept` avvia la Bozza deterministica e il Risk Gate sovrano.

**Flusso ordine.** accept → Bozza → Risk Gate → Coda di approvazione (modalità `auto` attiva per ora; `manual` con approvazione da CLI legata all'hash della bozza, Risk Gate ripetuto all'approvazione, scadenza a fine seduta) → invio seriale al broker a mercato aperto. Blocco del Risk Gate, rifiuto dell'utente o scadenza dell'approvazione = Rimando con motivazione nella chat del PM e Scheduled task al giorno di borsa successivo.

**Scheduled task.** Parametri: agente destinatario, chat (ticker o tema), quando, fonte, motivo, dati. Fonti: Alert esterni (prezzo, calendario, trimestrali), task programmati dagli agenti, messaggi del Market Analyst al PM, richieste manuali. Data limitata tra minimo e massimo configurabili in giorni di borsa. Il cursore dello scheduler avanza solo a consegna accettata; nessun retry automatico a raffica.

**Budget e concorrenza.** Budget del ciclo unico e generoso su messaggi e chiamate a subagent; budget proprio per ogni attivazione del Market Analyst. Cicli paralleli fino a `max_parallel` (default 3); Risk Gate, approvazione e invio serializzati.

**Sforzo e modelli.** Per agente: endpoint, modello, `effort` (default Analyst medio, PM alto, subagent basso, ticker_agent medio) tradotto nel parametro di ragionamento del provider o ignorato se non supportato.

**Schema del DB** (SQLite in WAL, migrazioni versionate):
- *Agenti e conversazioni*: agenti (configurazione, hash del prompt, stato `working`/`waiting`/`idle`), chat (agente, ticker o tema), messaggi (chat, autore, orario, testo; archivio originale e riassunti di compattazione).
- *Lavoro*: Scheduled task (stato, fonte, fusione), cicli, dossier versionati (`dossier_versions`: fatti con autore, ts, reference_date, confidenza, marcatura deterministica `stale`), proposte (`proposals`), state per ticker, watchlist.
- *Ordini e Trade*: ordini (bozza, hash, stato di approvazione, identificativo client, esiti broker), eventi dell'ordine, Trade (entrata, eventi di trailing, uscita e motivo), snapshot del portafoglio.
- *Registro*: chiamate LLM (agente, chat, token, costo, durata, riferimento a prompt e risposta), chiamate tool (agente, tool, parametri, risultato, errore), comandi CLI e modifiche di configurazione; testi grandi in una tabella di blob compressi e deduplicati per hash.
- *Dati finanziari*: anagrafica titoli (settore, industria), prezzi OHLCV, fondamentali, indicatori di bilancio, trimestrali, rating, insider, news, serie macro, calendario economico, performance settoriali; ogni riga con fonte e data di download e chiave unica.
- *Inbox*: avvisi per Luca.

**Conservazione.** Prezzi giornalieri 5 anni, poi settimanali fino a 10, poi mensili; barre orarie 90 giorni poi giornaliere; news complete 90 giorni poi titolo e sintesi; prompt e risposte 180 giorni poi metadati; chat, decisioni, ordini, Trade ed eventi per sempre. Job settimanale con vacuum incrementale; avviso oltre soglia.

**Errori.** 2 retry con attesa crescente; poi l'agente lo scrive in chat e il ciclo prosegue; PM in errore = Rimando con avviso; dati non aggiornati marcati come vecchi.

**Deploy.** Dev con `uv` e CLI. Prod con Docker Compose sul Minisforum: servizio `engine` (scheduler, agenti, esecuzione) con volume per il DB e `.env` montato; il servizio dashboard attuale resta fuori fino al cockpit.

## Testing Decisions

- **Cosa è un buon test:** verifica il comportamento esterno osservabile, non l'implementazione. Per il motore si controlla solo ciò che finisce nel DB (messaggi, state, ordini, Trade, Scheduled task, registro, Inbox) e cosa riceve il broker finto.
- **Punto principale (confermato da Luca):** il motore. Riceve uno Scheduled task e lavora fino alla decisione, con backend LLM a copione, fornitore dati, broker e orologio finti iniettati, su un DB temporaneo. Copre ciclo, messaggi, budget, fusione, Rimando, flusso ordine, approvazione, trailing, errori, arresto.
- **Funzioni pure:** Bozza dell'ordine, Risk Gate, trailing stop, traduttori, fusione e limiti degli Scheduled task, downsampling, testati direttamente con casi di confine.
- **CLI:** testata passando dallo stesso motore con un runner CLI.
- **Prova reale:** un solo smoke test manuale end-to-end con LLM veri e Alpaca paper, marcato e lanciato a mano, come i test di integrazione read-only su Alpaca già presenti.
- **Prior art nel repository:** fake del broker e test di integrazione Alpaca paper, test degli indicatori, test del grafo LangGraph con freschezza e completezza, test di storage SQLite.

## Out of Scope

Cockpit e interfaccia web; Valutatore (analisi di più ticker insieme); workspace per ticker con file e git; tool esposti via MCP e backend Claude Code o Pi; bridge Telegram; backtest degli agenti; PostgreSQL; short e uscite parziali; fonti social per il Sentiment; Portfolio Allocator e ottimizzazione di portafoglio; lezioni trasversali tra ticker e RAG; report di performance e benchmark; esecuzione su conto live (il sistema è broker-agnostico ma si collega al paper).

## Further Notes

- Le decisioni con motivazione stanno nel decision-log della wiki (righe 2026-11-18) e negli ADR 0001 e 0002; il vocabolario nel GLOSSARY.
- Prior art: OpenAlice (Trading as Git, guard al push, scheduler con cursore), TradingAgents (esiti e lezioni), ziyadal e Jiangge89 (checkpoint SQLite, costi, schemi Pydantic, approvazione), optimizer di Silvio Baratto (LLM sceglie parametri, il codice calcola).
- Da verificare prima del ticket sui dati: se rating degli analisti e insider sono disponibili con provider gratuiti via OpenBB o richiedono FMP.
- I system prompt li scrive l'agente come bozza nel ticket degli agenti; Luca li rivede.
