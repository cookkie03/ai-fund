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
L'agente che riceve gli Alert, apre il Ciclo di analisi, orchestra il lavoro degli Analyst, valida gli ordini e prende la decisione.
_Avoid_: CEO, PM reviewer

**Risk Analyst**:
L'Analyst che porta la tesi contraria (bear) e i dubbi di rischio prima della decisione del PM, e propone il prezzo di entrata dell'ordine. Non ha potere di veto e non valida gli ordini.
_Avoid_: Risk Gate, risk desk

**Risk Gate**:
Il controllo deterministico, non un agente, che dopo la validazione del PM verifica i limiti rigidi (esposizione, cassa, rischio per trade) e ha l'ultima parola: può solo bloccare, mai approvare né modificare.
_Avoid_: Risk Analyst, risk agent

**Analysis**:
Il contributo strutturato di un Analyst in un processo di analisi, con istante di osservazione.
_Avoid_: DeskOpinion, desk opinion

**Subagent**:
Un aiutante generico che un agente può invocare con un tool per un compito circoscritto. Non è un Agente e non ha chat proprie.

## Lavoro

**Alert**:
Evento che arriva al Portfolio Manager e fa partire un Ciclo di analisi (prezzo, calendario, `next_check_date`, richiesta manuale).
_Avoid_: trigger (per l'evento)

**Trigger engine**:
La parte del sistema che genera gli Alert.

**Ciclo di analisi**:
Tutto il lavoro che va da un Alert a una decisione del Portfolio Manager. Lo chiude solo il PM, quando il quadro basta o quando si raggiunge il tetto del ciclo; il Rimando è una decisione valida.
_Avoid_: research cycle, run

**Chat**:
La conversazione di un agente su un argomento: un ticker, o per il Market Analyst un genere di notizie. Ogni agente ha le sue chat; i messaggi inviati da un altro agente compaiono nella chat del destinatario. A ogni nuovo Ciclo di analisi la cronologia viene compattata e la chat riparte dal timestamp di fine del ciclo precedente fino al timestamp attuale.
_Avoid_: thread, canale

**Messaggio di apertura**:
Il messaggio che il PM invia a ogni Analyst quando apre un Ciclo di analisi.

**Rimando**:
Decisione del PM di non decidere e rianalizzare alla `next_check_date`. È anche l'esito deterministico quando il Ciclo di analisi esaurisce il Budget del ciclo.
_Avoid_: skip, pending (come esito)

**Budget del ciclo**:
Numero massimo, generoso, di messaggi e chiamate a subagent di tutti gli agenti in un Ciclo di analisi. Serve solo a fermare i loop: se viene raggiunto scatta il Rimando, con un avviso.

## Ordini

**Bracket order**:
Ordine strutturato con entrata a prezzo limite, take profit e stop loss. Scade alla `next_check_date` se non eseguito.
_Avoid_: ordine a mercato (non usato)

**Bozza dell'ordine**:
Il Bracket order completo calcolato in modo deterministico appena nello state ci sono gli input minimi (ticker, direzione, convinzione, prezzo attuale, ATR, capitale e posizioni). Gli Analyst responsabili la modificano solo tramite i Coefficienti; ogni modifica la ricalcola. Il PM la accetta o rimanda.

**Coefficienti dell'ordine**:
I parametri in unità di ATR da cui derivano i prezzi: `k_entry` e percentuale di rischio (responsabilità del Risk Analyst), `k_stop` e `k_tp` (responsabilità del Technical Analyst). Gli agenti scelgono coefficienti, mai prezzi.
_Avoid_: prezzo deciso dall'LLM

## Informazione

**Catalizzatore**:
Notizia o evento macro o di settore che può muovere il contesto (es. taglio dei tassi). Competenza del Market Analyst.

**Sentiment**:
Umore e posizionamento degli operatori su un titolo, da più fonti possibili (news, social, rating degli analisti, insider). Competenza del Sentiment Analyst. Le notizie sulla singola azienda sono Sentiment o Fundamental, mai Market, salvo che muovano l'intero settore.

**Rischio evento**:
Evento noto e datato sul singolo titolo (es. trimestrale) che può causare un gap. Competenza del Fundamental Analyst.
