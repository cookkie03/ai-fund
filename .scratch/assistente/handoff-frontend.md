# Handoff: pagina Assistente e mini Bridge (frontend, Impeccable, code-led)

Repo `/home/luca/trading-agent`. Parti dalla branch della pagina **`assistente-frontend`** (creata da `main`, che contiene shell, Terminale, Ufficio, Portafoglio e pagina del ticker in stile Legend) in un worktree tuo. Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: commit sul tuo branch di worktree; l'unione in `assistente-frontend` e la PR verso `main` le fa la sessione principale.

## Da leggere prima

`.scratch/assistente/brief.md` (decisioni di Luca), **`.scratch/assistente/handoff-backend.md` (contratto JSON vincolante)**, `PRODUCT.md`, `DESIGN.md`, `docs/frontend.md`, `.impeccable/design.json`, `.impeccable/surfaces/` (brief delle pagine già costruite), il codice di `frontend/src/shell/` (in particolare `bridge.tsx`, `shell-state.tsx`, `app-shell.tsx`, `nav.ts`), `frontend/src/features/office/` e `frontend/src/features/dossier/` (modello per adattatori, fonti oneste e comandi con conferma).

## Cosa costruire

1. **Pagina Assistente** (`/` e `/assistente`; oggi `/` reindirizza al Terminale, in `App.tsx`; in `nav.ts` segna la pagina come costruita). Tre zone insieme:
   - **Elenco delle conversazioni** a sinistra, come l'app di Claude: nuova conversazione, ricerca, rinomina, archivio, indicatore di turno in corso e di azioni in attesa.
   - **Briefing** in testa alla pagina (`/v1/read/briefing`): sintesi del Bridge, variazione del portafoglio, conteggi, voci recenti con severità. Ogni voce ha «Chiedi al Bridge», che apre o continua una conversazione con quel riferimento nel contesto. «Segna come letto» → `mark_briefing_seen`. Il briefing occupa poco quando non c'è niente di nuovo e si comprime quando la conversazione è attiva.
   - **Conversazione** al centro: messaggi di Luca, del Bridge e risposte degli agenti inoltrate (`agent_relay`, con l'avatar dell'agente), riferimenti cliccabili (ticker → `/ticker/:symbol`, posizione e ordine → Portafoglio, proposta → Ufficio, agente → `/ufficio/:agent`), stato del turno dal vivo (`bridge.status`: sta pensando, sta usando il tool X), pulsante Stop, errori leggibili. **Card delle azioni**: comando in parole, payload leggibile, preview del Risk Gate con i motivi verbatim, «Conferma» e «Annulla»; la conferma usa lo stesso schema di conferma esplicita delle azioni del Portafoglio (`bridge_action_decide` con `confirm:true`); stati eseguita, rifiutata con motivi, annullata. Composer con invio, a capo con Shift+Invio, e `@agente` che chiede al Bridge di scrivere a quell'agente.
   - **Pannello laterale dello stato vivo** a destra, dalle letture esistenti: valore del portafoglio e P&L di oggi, cassa, agenti al lavoro, proposte in attesa del PM, azioni del Bridge in attesa, Halt, connessione al Runtime.
2. **Mini Bridge ovunque.** Il pannello Bridge dello shell (`shell/bridge.tsx`) diventa la stessa conversazione dell'Assistente: mostra la conversazione corrente (o l'ultima), permette di cambiarla o aprirne una nuova, e invia con `context: {page, ticker, ref}` della pagina aperta (Terminale con ticker, pagina del ticker, Portafoglio con la posizione selezionata, Ufficio con l'agente). Sulla pagina Assistente il pannello dello shell non si duplica. Togli l'avviso «non ancora attivo» quando il Runtime espone le letture del Bridge; finché no, mantieni il fallback attuale `@agente` → `say` nel topic `cockpit` con uno stato «non disponibile» che nomina l'endpoint mancante.
3. **Telefono 390 px:** Assistente con conversazione a schermo intero, elenco delle conversazioni e stato vivo in fogli; briefing compatto in testa.

## Ambiente

PC Linux headless (`192.168.68.107`, utente `luca`); Luca usa un MacBook e vuole l'esperienza Impeccable completa (`IMPECCABLE_QUESTION_FORCE=1`). Porte: Runtime sintetico **8773** (`uv run python scripts/dev_cockpit_server.py --port 8773 --db data/dev-cockpit-assistente-fe.db`), Vite **5180** (`COCKPIT_PORT=5180 COCKPIT_RUNTIME_URL=http://127.0.0.1:8773 npx vite`); controlla con `ss -ltn`. Se colleghi `node_modules` con un symlink fuori dal worktree, Vite può dare un 403 sul font: è innocuo. Comandi per Luca sul Mac:

```bash
ssh -N -L 5180:127.0.0.1:5180 luca@192.168.68.107
```
```bash
open http://127.0.0.1:5180/
```

## Decisioni già prese

Mode **Operate**, build **code-led**, mondo **Legend**: estendi `DESIGN.md`, nessuna nuova direzione. Riferimenti: l'app di Claude per conversazioni e composer, Linear per densità e liste, il briefing come la testata di un report mattutino professionale (non una dashboard di tessere). Il Bridge è un collega, non un chatbot di assistenza: niente saluti finti né emoji. Il Risk Gate è sovrano: il Bridge propone, Luca conferma, il Runtime ricontrolla.

## Flusso Impeccable

`impeccable context --target frontend/src` una volta, `reference/new-work.md`, surface brief per Assistente e mini Bridge, `reference/craft-floor.md` prima di ogni modifica UI; costruzione con tutti gli stati (caricamento, nessuna conversazione, briefing vuoto, turno in corso, tool in uso, agent_relay, azione in attesa / eseguita / rifiutata dal Risk Gate / annullata, errore di budget, Halt, Runtime irraggiungibile, endpoint del Bridge non ancora esposto), desktop e 390 px; verifica con first-viewport, `impeccable detect`, Playwright, finish review, critique, audit e aggiornamento di `DESIGN.md`. Se i subagenti non rispondono, valutazioni inline secondo le rubric e dillo nel report.

## Dipendenze

Il backend lo costruisce in parallelo un'altra sessione sulla branch `assistente-frontend`. Finché non c'è: adattatori tipizzati **con esattamente i nomi del contratto**, stati «non disponibile» che nominano l'endpoint, nessun dato finto in produzione; fixture solo dietro una variabile del dev server (`COCKPIT_ASSISTANT_FIXTURES`, come `COCKPIT_OFFICE_FIXTURES` e `COCKPIT_TICKER_FIXTURES` in `vite.config.ts`). Le fixture devono coprire ogni stato elencato sopra, compresi gli eventi SSE simulati di un turno.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere sorgenti; `graphify update .` dopo modifiche. Serena per il codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non toccare `runtime/`, `storage/`, `workflows/`, `tools/`, `execution/`, `scripts/`, `config/`, `prompts/`.
- Non committare `data/*.db*`, `.serena/`, `frontend/tsconfig.tsbuildinfo`.
- Controlli: `npx tsc -b --noEmit` e `npm run build` in `frontend/`.
- Annota in `.scratch/assistente/wiki-notes-frontend.md` cosa registrare nella wiki e quali adattatori aspettano il backend.
