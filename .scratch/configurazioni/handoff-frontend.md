# Handoff: pagina Configurazioni (frontend, Impeccable, code-led)

Repo `/home/luca/trading-agent`. Parti dalla branch della pagina **`configurazioni-frontend`** (creata da `main`: shell, Terminale, Ufficio, Portafoglio e pagina del ticker in stile Legend) in un worktree tuo. Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: commit sul tuo branch di worktree; l'unione in `configurazioni-frontend` e la PR verso `main` le fa la sessione principale.

## Da leggere prima

`.scratch/configurazioni/brief.md` (decisioni di Luca, compresa la collocazione per coerenza), **`.scratch/configurazioni/handoff-backend.md` (contratto JSON vincolante)**, `PRODUCT.md`, `DESIGN.md`, `docs/frontend.md`, `.impeccable/design.json`, `.impeccable/surfaces/`, il codice di `frontend/src/shell/` (`nav.ts`, `App.tsx`), `frontend/src/features/portfolio/` e `frontend/src/pages/portafoglio/` (la modifica dei limiti di rischio con preview, conferma, motivo e storico: **il modello da riusare**), `frontend/src/features/office/` (fonti oneste).

## Cosa costruire

Pagina **`/configurazioni`** (in `nav.ts` segnala come costruita), come le impostazioni di un prodotto professionale (riferimenti: Linear, Raycast, Impostazioni di macOS; densità da strumento, non da modulo web):

1. **Indice** a sinistra con le sezioni: Agenti, Provider e chiavi, Mercato e orari, Dati e archivio, Salute del Runtime; più un gruppo **«Altrove»** con collegamenti a Limiti di rischio (Portafoglio, scheda «Rischio e vincoli»), Fonti delle notizie (Notizie), Watchlist (Terminale), Costi e token (Ufficio). Sezioni nell'URL (`/configurazioni/agenti`, ecc.).
2. **Impostazioni** (`settings`): ogni voce con etichetta, descrizione, valore, default, unità, limiti, segno «modificata» rispetto al default, segno «vale dal prossimo riavvio». Modifica in bozza → **preview** (`update_settings` con `dry_run:true`: vecchio → nuovo, esito per voce, avvisi) → motivo obbligatorio → conferma (esplicita per `capital:true`, come nel Portafoglio). Banner con le modifiche in attesa di riavvio. **Storico** con ripristino di una versione.
3. **Agenti**: tabella degli agenti (`agent_configs`) con modello, endpoint, effort, budget, costo di oggi (link all'Ufficio per i dettagli) e versione del prompt; per ogni agente, editor del **prompt** (monospace, conteggio caratteri) con **diff** rispetto alla versione attiva prima della conferma, motivo, storico delle versioni con ripristino, avviso «vale dal prossimo ciclo».
4. **Provider e chiavi** (`secrets`): per ogni chiave stato (impostata da store / da ambiente / mancante), ultime 4 cifre, data, esito dell'ultimo test; **campo in sola scrittura** (tipo password, mai precompilato, svuotato dopo l'invio, nessun valore in stato globale, cache delle query, log o URL), conferma esplicita per le chiavi del broker, «Prova connessione», «Rimuovi». Dopo il salvataggio mostra solo l'esito restituito.
5. **Dati e archivio**: retention, dimensione del DB e WAL rispetto alla soglia, backup con «Crea backup» ed elenco.
6. **Salute del Runtime** (`runtime_health`): versione e commit, uptime, job con ultima/prossima esecuzione ed errori, ultimi errori, client SSE, stato di broker e provider LLM; aggiornamento dal vivo (`health.changed`).
7. **Telefono 390 px**: indice come elenco, sezione come pagina, editor del prompt a schermo intero, diff impilato.

## Ambiente

PC Linux headless (`192.168.68.107`, utente `luca`); Luca usa un MacBook e vuole l'esperienza Impeccable completa (`IMPECCABLE_QUESTION_FORCE=1`). Porte: Runtime sintetico **8777** (`uv run python scripts/dev_cockpit_server.py --port 8777 --db data/dev-cockpit-configurazioni-fe.db`), Vite **5182** (`COCKPIT_PORT=5182 COCKPIT_RUNTIME_URL=http://127.0.0.1:8777 npx vite`); controlla con `ss -ltn`. Un 403 di Vite sul font con `node_modules` collegato da fuori è innocuo. Comandi per Luca sul Mac:

```bash
ssh -N -L 5182:127.0.0.1:5182 luca@192.168.68.107
```
```bash
open http://127.0.0.1:5182/configurazioni
```

## Decisioni già prese

Mode **Operate**, build **code-led**, mondo **Legend**: estendi `DESIGN.md`, nessuna nuova direzione. Configurazioni non duplica ciò che vive in altre pagine: lo collega. Le chiavi non tornano mai al frontend.

## Flusso Impeccable

`impeccable context --target frontend/src` una volta, `reference/new-work.md`, surface brief per Configurazioni, `reference/craft-floor.md` prima di ogni modifica UI; costruzione con tutti gli stati (caricamento, valori di default, modifiche in bozza, preview con voce rifiutata, conferma per `capital`, modifica in attesa di riavvio, storico vuoto, diff del prompt lungo, chiave mancante / da ambiente / test fallito, job in errore, DB oltre soglia, Runtime irraggiungibile, endpoint non ancora esposto), desktop e 390 px; verifica con first-viewport, `impeccable detect`, Playwright, finish review, critique, audit e aggiornamento di `DESIGN.md`. Se i subagenti Sonnet e Haiku danno «model not found», valutazioni inline secondo le rubric e dillo nel report.

## Dipendenze

Il backend arriverà dopo, da una sessione CLI di Luca sulla stessa branch. Finché non c'è: adattatori tipizzati **con esattamente i nomi del contratto**, stati «non disponibile» che nominano l'endpoint, nessun dato finto in produzione; fixture solo dietro `COCKPIT_SETTINGS_FIXTURES` (come le altre in `vite.config.ts`). Tocca lo shell solo per rotta e collegamenti.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere sorgenti; `graphify update .` dopo modifiche. Serena per il codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non toccare `runtime/`, `storage/`, `workflows/`, `tools/`, `execution/`, `scripts/`, `config/`, `prompts/`, `data/`.
- Non committare `data/*.db*`, `.serena/`, `frontend/tsconfig.tsbuildinfo`, `.env`.
- Controlli: `npx tsc -b --noEmit` e `npm run build` in `frontend/`.
- Annota in `.scratch/configurazioni/wiki-notes-frontend.md` cosa registrare nella wiki e quali adattatori aspettano il backend.
