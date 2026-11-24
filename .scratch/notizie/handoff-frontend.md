# Handoff: pagina Notizie (frontend, Impeccable, code-led)

Repo `/home/luca/trading-agent`. Parti dalla branch della pagina **`notizie-frontend`** (creata da `main`: shell, Terminale, Ufficio, Portafoglio e pagina del ticker in stile Legend) in un worktree tuo. Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: commit sul tuo branch di worktree; l'unione in `notizie-frontend` e la PR verso `main` le fa la sessione principale.

## Da leggere prima

`.scratch/notizie/brief.md` (decisioni di Luca), **`.scratch/notizie/handoff-backend.md` (contratto JSON vincolante)**, `PRODUCT.md`, `DESIGN.md`, `docs/frontend.md`, `.impeccable/design.json`, `.impeccable/surfaces/` (brief delle pagine già costruite), il codice di `frontend/src/shell/` (`nav.ts`, `App.tsx`), `frontend/src/features/office/` e `frontend/src/features/dossier/` (modello per adattatori, fonti oneste e comandi).

## Cosa costruire

Pagina **`/notizie`** (in `nav.ts` segnala come costruita):

1. **Flusso** a sinistra/centro, denso come un terminale di notizie professionale: ora, fonte e provider, titolo, ticker come etichette, segni d'uso (letta, citata, inoltrata dagli agenti), notizie nuove in arrivo dal vivo (`news.ingested`) senza far saltare la lettura (barra «N nuove»). Filtri: ambito (tutte, portafoglio, watchlist), ticker, tema, fonte, provider, ricerca testuale; filtri nell'URL. Paginazione infinita con `next_before`.
2. **Lettore** a destra: titolo, fonte, data, ticker (link a `/ticker/:symbol` e al Terminale), sommario o testo, link all'originale; sezione **uso da parte degli agenti** (`usage_detail`: chi, quando, letta/citata/inoltrata, link al ciclo e alla chat in `/ufficio/:agent`); azione **Inoltra** con scelta di agente o ticker (ticker → agente del ticker), nota obbligatoria, anteprima di cosa arriverà nella chat; esito e messaggio nella cronologia d'uso.
3. **Calendario** macro ed earnings (`/v1/read/calendar`): prossimi giorni, importanza, attuale/atteso/precedente, evidenza per i ticker in portafoglio e watchlist. Scegli tu la collocazione (colonna, scheda o striscia), giustificandola nel surface brief.
4. **Fonti**: pannello o foglio con lo stato delle fonti (`news_sources`: ok, errore con motivo, non disponibile), aggiungere e togliere un feed RSS, abilitare/disabilitare, aggiorna ora.
5. **Collegamenti**: dalla pagina del ticker e dal Terminale, «Notizie su questo ticker» porta a `/notizie?ticker=SYM`.
6. **Telefono 390 px**: flusso a schermo intero, lettore come pagina o foglio, filtri in un foglio, calendario come scheda.

## Ambiente

PC Linux headless (`192.168.68.107`, utente `luca`); Luca usa un MacBook e vuole l'esperienza Impeccable completa (`IMPECCABLE_QUESTION_FORCE=1`). Porte: Runtime sintetico **8775** (`uv run python scripts/dev_cockpit_server.py --port 8775 --db data/dev-cockpit-notizie-fe.db`), Vite **5181** (`COCKPIT_PORT=5181 COCKPIT_RUNTIME_URL=http://127.0.0.1:8775 npx vite`); controlla con `ss -ltn`. Un 403 di Vite sul font con `node_modules` collegato da fuori è innocuo. Comandi per Luca sul Mac:

```bash
ssh -N -L 5181:127.0.0.1:5181 luca@192.168.68.107
```
```bash
open http://127.0.0.1:5181/notizie
```

## Decisioni già prese

Mode **Operate**, build **code-led**, mondo **Legend**: estendi `DESIGN.md`, nessuna nuova direzione. Riferimenti: terminali di notizie professionali (densità, ora e fonte sempre visibili), lettori come Reeder per la leggibilità del testo, Linear per filtri e liste. Niente sintesi LLM nella pagina. L'inoltro è il parere di un collega, non un ordine.

## Flusso Impeccable

`impeccable context --target frontend/src` una volta, `reference/new-work.md`, surface brief per Notizie, `reference/craft-floor.md` prima di ogni modifica UI; costruzione con tutti gli stati (caricamento, nessuna notizia per il filtro, notizie nuove in arrivo, notizia senza testo, notizia mai usata, inoltro riuscito e rifiutato, fonte in errore, OpenBB non disponibile, calendario vuoto, Runtime irraggiungibile, endpoint non ancora esposto), desktop e 390 px; verifica con first-viewport, `impeccable detect`, Playwright, finish review, critique, audit e aggiornamento di `DESIGN.md`. I subagenti Sonnet e Haiku hanno dato «model not found» nell'ultima sessione: se succede, valutazioni inline secondo le rubric e dillo nel report.

## Dipendenze

Il backend arriva da un'altra sessione sulla branch `notizie-frontend`. Finché non c'è: adattatori tipizzati **con esattamente i nomi del contratto**, stati «non disponibile» che nominano l'endpoint, nessun dato finto in produzione; fixture solo dietro `COCKPIT_NEWS_FIXTURES` (come le altre in `vite.config.ts`), con eventi SSE simulati per le notizie in arrivo. Se `assistente-frontend` viene unito su `main` mentre lavori, non serve che lo porti dentro: l'unione la gestisce la sessione principale; tocca lo shell solo per rotta e collegamenti.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere sorgenti; `graphify update .` dopo modifiche. Serena per il codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non toccare `runtime/`, `storage/`, `workflows/`, `tools/`, `execution/`, `scripts/`, `config/`, `prompts/`, `data/`.
- Non committare `data/*.db*`, `.serena/`, `frontend/tsconfig.tsbuildinfo`.
- Controlli: `npx tsc -b --noEmit` e `npm run build` in `frontend/`.
- Annota in `.scratch/notizie/wiki-notes-frontend.md` cosa registrare nella wiki e quali adattatori aspettano il backend.
