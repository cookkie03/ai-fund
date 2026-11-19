# Glossario — Trading Agent

Linguaggio di dominio del progetto. Requisiti e decisioni estese vivono nella wiki adiacente (`../trading-agent-wiki/`).

## Agenti

**Agente**:
Uno dei sei ruoli autonomi del sistema: Market Analyst, Sentiment Analyst, Technical Analyst, Fundamental Analyst, Risk Analyst, Portfolio Manager. Gli agenti sono pari: possono scambiarsi messaggi come colleghi nello stesso ufficio.
_Avoid_: desk, bot

**Analyst**:
Uno dei cinque agenti specialisti (Market, Sentiment, Technical, Fundamental, Risk). Produce un'Analysis sulla propria specialità ma può esprimersi su tutto. Ragiona con un LLM; i numeri li ottiene da tool deterministici.
_Avoid_: desk, desk analyst

**Portfolio Manager (PM)**:
L'agente che riceve gli Scheduled task sui ticker, apre il Ciclo di analisi, orchestra il lavoro degli Analyst, valida gli ordini e prende la decisione.
_Avoid_: CEO, PM reviewer

**Risk Analyst**:
L'Analyst che porta la tesi contraria (bear) e i dubbi di rischio prima della decisione del PM, e sceglie il coefficiente di entrata e la percentuale di rischio dell'ordine. Non ha potere di veto e non valida gli ordini.
_Avoid_: Risk Gate, risk desk

**Risk Gate**:
Il controllo deterministico, non un agente, che dopo la validazione del PM verifica i limiti rigidi (esposizione, cassa, rischio per trade) e ha l'ultima parola: può solo bloccare, mai approvare né modificare.
_Avoid_: Risk Analyst, risk agent

**Analysis**:
Il contributo strutturato di un Analyst in un processo di analisi, con istante di osservazione.
_Avoid_: DeskOpinion, desk opinion

**Valutatore**:
Livello tra PM e Analyst che coordina l'analisi di più ticker insieme (es. trimestrali di molti titoli, analisi comparate). Previsto dopo l'MVP.

**Subagent**:
Un aiutante generico che un agente può invocare con un tool per un compito circoscritto. Non è un Agente e non ha chat proprie.

## Lavoro

**Scheduled task**:
L'unico modo in cui un agente viene richiamato: il PM su un ticker o il Market Analyst su un tema. Porta solo i parametri necessari (agente, chat, quando, fonte, motivo, dati). Nasce da un Alert, da un controllo che un agente si è programmato in precedenza, da un messaggio del Market Analyst al PM o da una richiesta manuale. Un traduttore deterministico, uno per fonte, lo trasforma nel prompt di apertura. Se il ticker è già in analisi entra come messaggio nel ciclo aperto; due Scheduled task in coda sulla stessa chat si fondono.
_Avoid_: next check date, controllo programmato, trigger

**Alert**:
Evento di una fonte esterna (prezzo, calendario, trimestrale) che viene incapsulato in uno Scheduled task immediato.

**Trigger engine**:
La parte del sistema che crea gli Scheduled task dalle fonti e li consegna quando scadono.

**Ciclo di analisi**:
Tutto il lavoro che va da uno Scheduled task del PM a una sua decisione del Portfolio Manager. Lo chiude solo il PM, quando il quadro basta o quando si raggiunge il tetto del ciclo; il Rimando è una decisione valida.
_Avoid_: research cycle, run

**Chat**:
La conversazione di un agente su un argomento: un ticker, o per il Market Analyst un genere di notizie. Ogni agente ha le sue chat; i messaggi inviati da un altro agente compaiono nella chat del destinatario. A ogni nuovo Ciclo di analisi la cronologia viene compattata e la chat riparte dal timestamp di fine del ciclo precedente fino al timestamp attuale.
_Avoid_: thread, canale

**Messaggio di apertura**:
Il messaggio che il PM invia a ogni Analyst quando apre un Ciclo di analisi.

**Rimando**:
Decisione del PM di non decidere e rianalizzare a uno Scheduled task futuro. È anche l'esito deterministico quando il Ciclo di analisi esaurisce il Budget del ciclo, quando il Risk Gate blocca l'ordine o quando l'utente lo rifiuta.
_Avoid_: skip, pending (come esito)

**Budget del ciclo**:
Numero massimo, generoso, di messaggi e chiamate a subagent di tutti gli agenti in un Ciclo di analisi. Serve solo a fermare i loop: se viene raggiunto scatta il Rimando, con un avviso.

## Ordini

**Bracket order**:
Ordine strutturato con entrata a prezzo limite, take profit e stop loss. Scade allo Scheduled task successivo sul ticker se non eseguito.
_Avoid_: ordine a mercato (non usato)

**Bozza dell'ordine**:
Il Bracket order completo calcolato in modo deterministico appena nello state ci sono gli input minimi (ticker, direzione, convinzione, prezzo attuale, ATR, capitale e posizioni). Gli Analyst responsabili la modificano solo tramite i Coefficienti; ogni modifica la ricalcola. Il PM la accetta o rimanda.

**Coefficienti dell'ordine**:
I parametri in unità di ATR da cui derivano i prezzi: `k_entry` e percentuale di rischio (responsabilità del Risk Analyst), `k_stop` e `k_tp` (responsabilità del Technical Analyst). Gli agenti scelgono coefficienti, mai prezzi.
_Avoid_: prezzo deciso dall'LLM

**Coda di approvazione**:
Dove attendono gli ordini che hanno superato il Risk Gate. Un ordine parte verso il broker solo dopo l'approvazione dell'utente; se la Bozza cambia, l'approvazione decade. Un'impostazione permette di saltare l'approvazione e inviare subito.

**Trailing stop**:
Spostamento automatico e deterministico dello stop loss quando il prezzo supera una soglia di guadagno calcolata da formula. Nessun LLM interviene.

**Trade**:
La vita di una posizione dall'entrata all'uscita, con ogni evento registrato: esecuzione, spostamenti dello stop, uscita per take profit, stop loss, vendita del PM o scadenza.

**Arresto (halt)**:
Interruttore d'emergenza dell'utente: ferma il Trigger engine e blocca l'invio di nuovi ordini finché non viene ripreso.
_Avoid_: pausa

## Informazione

**Catalizzatore**:
Notizia o evento macro o di settore che può muovere il contesto (es. taglio dei tassi). Competenza del Market Analyst.

**Sentiment**:
Umore e posizionamento degli operatori su un titolo, da più fonti possibili (news, social, rating degli analisti, insider). Competenza del Sentiment Analyst. Le notizie sulla singola azienda sono Sentiment o Fundamental, mai Market, salvo che muovano l'intero settore.

**Rischio evento**:
Evento noto e datato sul singolo titolo (es. trimestrale) che può causare un gap. Competenza del Fundamental Analyst.

## Runtime

**Runtime**:
L'unico processo sempre acceso del sistema. Possiede il DB in scrittura, il Trigger engine, i Cicli di analisi, l'order flow e la connessione al broker. Un Runtime per account broker. Decisione in `docs/adr/0003-runtime-unico-writer-event-driven.md`.
_Avoid_: motore, core service, cache, engine (per il processo)

**Client**:
Qualunque interfaccia che parla con il Runtime senza possedere stato proprio: CLI, frontend (cockpit), bridge Telegram. Non apre il DB e non ha credenziali broker.

**Comando**:
Richiesta tipizzata di un Client per cambiare lo stato (es. approvare un ordine, Arresto, `Say`). Il Runtime la valida, la esegue una sola volta per `command_id` e la registra nell'Event log. I comandi che toccano il capitale richiedono una conferma esplicita.
_Avoid_: azione, chiamata API

**Lettura**:
Richiesta di sola consultazione a un read model del Runtime (portafoglio, ordini, cicli, inbox, health). Non modifica mai lo stato.
_Avoid_: query (nel linguaggio di dominio)

**Evento**:
Fatto di dominio già avvenuto e committato (es. `order.submitted`, `cycle.closed`). Il Runtime lo scrive nell'Event log e lo pubblica ai Client dopo il commit.
_Avoid_: notifica, alert (un Alert è un input esterno, non un Evento)

**Event log**:
Tabella append-only `events` del DB: audit di Comandi ed Eventi, e fonte del replay per i Client che si riconnettono. Non sostituisce le tabelle di stato, che restano la verità.
