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
L'agente che riceve gli Alert, avvia ogni processo di analisi, valida il lavoro degli Analyst e prende la decisione. È pari agli altri agenti in tutto il resto.
_Avoid_: CEO, orchestratore, PM reviewer

**Risk Analyst**:
L'Analyst che porta la tesi contraria (bear) e i dubbi di rischio prima della decisione del PM. Non ha potere di veto.
_Avoid_: Risk Gate, risk desk

**Risk Gate**:
Il controllo deterministico, non un agente, che dopo la decisione del PM verifica i limiti di rischio e ha l'ultima parola: può solo bloccare, mai approvare al posto del PM.
_Avoid_: Risk Analyst, risk agent

**Analysis**:
Il contributo strutturato di un Analyst in un processo di analisi, con istante di osservazione.
_Avoid_: DeskOpinion, desk opinion

## Lavoro

**Alert**:
Evento che arriva al Portfolio Manager e fa partire un Ciclo di analisi (prezzo, calendario, `next_check_date`, richiesta manuale).
_Avoid_: trigger (per l'evento)

**Trigger engine**:
La parte del sistema che genera gli Alert.

**Ciclo di analisi**:
Tutto il lavoro che va da un Alert a una decisione del Portfolio Manager. Lo chiude solo il PM, quando il quadro basta o quando si raggiunge il tetto del ciclo; «pending» è una decisione valida.
_Avoid_: research cycle, run

**Chat**:
La conversazione di un agente su un argomento: un ticker, o per il Market Analyst un genere di notizie. Ogni agente ha le sue chat; i messaggi inviati da un altro agente compaiono nella chat del destinatario. A ogni nuovo Ciclo di analisi la cronologia viene compattata e la chat riparte dal timestamp di fine del ciclo precedente fino al timestamp attuale.
_Avoid_: thread, canale

## Informazione

**Catalizzatore**:
Notizia o evento macro o di settore che può muovere il contesto (es. taglio dei tassi). Competenza del Market Analyst.

**Sentiment**:
Umore e posizionamento degli operatori su un titolo, da più fonti possibili (news, social, rating degli analisti, insider). Competenza del Sentiment Analyst. Le notizie sulla singola azienda sono Sentiment o Fundamental, mai Market, salvo che muovano l'intero settore.

**Rischio evento**:
Evento noto e datato sul singolo titolo (es. trimestrale) che può causare un gap. Competenza del Fundamental Analyst.
