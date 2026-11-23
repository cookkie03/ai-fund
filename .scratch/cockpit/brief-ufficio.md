# Brief Impeccable: Ufficio (confermato da Luca il 2026-11-22)

Mode: **Operate**. Build path: **code-led**. Mondo visivo: quello già stabilito e approvato (stile **Legend**, `DESIGN.md` e `.impeccable/design.json` su `feat/cockpit-frontend`). È una nuova superficie dentro un mondo esistente: niente nuovo giro di direzioni, si estende il sistema. Contesto: `PRODUCT.md`, `docs/frontend.md`, `docs/dashboard.md`.

## Job e pubblico

Luca entra nell'ufficio autonomo come **collega jolly**. L'Ufficio gli mostra chi sta lavorando e su cosa, gli fa leggere ogni conversazione degli agenti e vedere in diretta le chiamate ai tool, e gli permette di intervenire: scrivere a un agente, assegnargli un task. Il motore non lo aspetta: le sue parole sono un parere che gli agenti pesano.

## Riferimenti di qualità

App di Claude (conversazione e blocchi dei tool), Slack (agenti e conversazioni come canali), Linear (densità con calma, stati). Stile Legend: tessere grafite su fondo quasi nero, avatar pieni, controlli segmentati, raggi concentrici 12/8/6/4.

## Struttura (scelta di Luca: panoramica + chat)

1. **Panoramica dell'ufficio** (vista d'ingresso): una tessera per agente con avatar e ruolo, stato (sta lavorando, in attesa, inattivo), task o ciclo corrente con ticker, ultima attività e da quanto, costo e token di oggi. Si aggiorna dal vivo.
2. **Vista agente** (clic su una tessera), tre zone come Slack:
   - **sinistra**: gli agenti (per passare dall'uno all'altro) e, sotto l'agente scelto, **le sue chat**. Ogni agente ha più chat (topic): per ticker, per ciclo, con Luca, ecc. Ogni chat mostra titolo, ultimo messaggio e quando;
   - **centro**: la conversazione della chat scelta, in stile app di Claude, con autore di ogni messaggio (agente, altro agente, Luca); in fondo il campo per scrivere (comando `say` sul topic);
   - **destra**: lo **stream delle chiamate ai tool** di quell'agente, dal vivo. Ogni chiamata è un blocco compatto (tool, argomenti principali, durata, esito ok/errore) che si espande per mostrare input e output completi, come nell'app di Claude. Se il contenuto è stato compattato dalla retention, lo dice.
3. **Azioni di Luca**: scrivere nella chat (`say`), assegnare un task a un agente su un ticker (`enqueue_task`), vedere costi e token per agente (oggi e periodo). Niente pausa degli agenti per ora.

## Stati

Caricamento (skeleton), ufficio fermo (nessun agente attivo), agente senza chat, chat vuota, chiamata ai tool in corso, chiamata fallita, contenuto compattato dalla retention, stream disconnesso (età visibile), Halt, Runtime irraggiungibile, rifiuto di un comando (`ok: false` con ragioni). Mai dati finti in produzione; per sviluppo il dev server.

## Responsive

Telefono (390 px): panoramica come lista; vista agente come schede Chat / Tool, con le chat dell'agente in un selettore. Tutto usabile da tastiera; i pannelli si nascondono con le stesse scorciatoie del Terminale.

## Backend necessario (nel Runtime)

Vedi `.scratch/cockpit/handoff-backend-ufficio.md`: elenco agenti con stato, chat per agente, chiamate ai tool, uso e costi, eventi SSE dal vivo, scenario di sviluppo.

## Fuori scope

Bridge funzionante, pausa degli agenti, sezione Evaluation completa (qui solo costi e token per agente), altre pagine.

## Chiusura (regola Impeccable)

Unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
