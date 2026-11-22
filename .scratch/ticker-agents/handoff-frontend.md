# Handoff: Ufficio a due livelli e pagina del ticker (Impeccable, code-led)

Repo `/home/luca/trading-agent`, branch di partenza `feat/cockpit-frontend` (shell, Terminale e Ufficio in stile Legend). Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: commit sul tuo branch, non su `feat/cockpit-frontend` (l'unione la decide Luca).

## Da leggere prima

`.scratch/ticker-agents/brief.md` (decisioni di Luca), **`.scratch/ticker-agents/handoff-backend.md` (contratto JSON vincolante)**, `PRODUCT.md`, `docs/frontend.md`, `DESIGN.md`, `.impeccable/design.json`, `.scratch/cockpit/brief-ufficio.md`, il codice di `frontend/src/pages/ufficio/` e `frontend/src/features/office/` (modello per adattatori e fonti oneste).

## Cosa costruire

1. **Ufficio riprogettato a due livelli.**
   - Panoramica: la **squadra centrale** (PM e specialist) e il **desk degli agenti del ticker** (uno per ticker: ticker, stato, direzione e conviction, stato della proposta, costo di oggi, ultima attività). La gerarchia PM → agenti del ticker → specialist si legge dalla composizione, non da un grafo decorativo. Il desk deve reggere da 3 a 40 ticker (lista densa con filtri: in analisi, in attesa del PM, in portafoglio, inattivi).
   - **Proposte in attesa del PM** in evidenza (ticker, direzione, conviction, sizing, R:R, da quanto aspetta). Luca può decidere al posto del PM (`decide_proposal` con `confirm:true`, stesso percorso e Risk Gate).
   - Vista agente: per un agente del ticker mostra la sua chat, i tool e un link forte alla scheda `/ticker/:symbol`; per il PM mostra anche la coda delle proposte.
   - Mantieni tutto ciò che funziona oggi (più chat per agente, tool espandibili, scrivi, assegna task, costi e token).
2. **Pagina `/ticker/:symbol`: la scheda del ticker.** Dossier professionale, sempre aggiornato, a cui fanno riferimento gli agenti:
   - intestazione: ticker, nome, settore, prezzo, posizione (se investita), stato della scheda, agente del ticker con il suo stato;
   - tesi (direzione, conviction, pro e contro, catalizzatori con data, prossima verifica);
   - proposta operativa e verdetto del Risk Gate con le regole;
   - analisi di ogni specialist con autore, data, confidenza; i fatti vecchi o superati arretrano visivamente ma restano leggibili;
   - storico decisioni, lezioni dai trade passati, storico versioni;
   - note di Luca con composer (`add_dossier_note`), visibilmente firmate;
   - collegamenti: grafico nel Terminale, chat del ticker nell'Ufficio, posizione nel Portafoglio.
   Raggiungibile da ovunque: watchlist e intestazione del Terminale, posizioni del Portafoglio (quando unito), topic per ticker dell'Ufficio, ricerca dello shell se esiste. Telefono 390 px: sezioni impilate con indice.

## Ambiente

PC Linux headless (`192.168.68.107`, utente `luca`); Luca usa un MacBook e vuole l'esperienza Impeccable completa (`IMPECCABLE_QUESTION_FORCE=1`). Porte: Runtime sintetico **8771** (`uv run python scripts/dev_cockpit_server.py --port 8771 --db data/dev-cockpit-ticker-fe.db`), Vite **5179** (`COCKPIT_PORT=5179 COCKPIT_RUNTIME_URL=http://127.0.0.1:8771 npx vite`); controlla con `ss -ltn`. Comandi per Luca sul Mac:

```bash
ssh -N -L 5179:127.0.0.1:5179 luca@192.168.68.107
```
```bash
open http://127.0.0.1:5179/ufficio
```

## Decisioni già prese

Mode **Operate**, build **code-led**, mondo **Legend**: estendi `DESIGN.md`, nessuna nuova direzione. Riferimenti: Ufficio come Linear, Slack e app di Claude; scheda del ticker come una pagina di ricerca professionale (densità di un report d'analista, leggibilità di Linear). Il ticker propone, il PM decide, il Risk Gate è sovrano.

## Flusso Impeccable

`impeccable context --target frontend/src` una volta, `reference/new-work.md`, surface brief per Ufficio rivisto e pagina del ticker, `reference/craft-floor.md` prima di ogni modifica UI; costruzione con tutti gli stati (caricamento, scheda vuota, nessun agente del ticker, fatti vecchi, proposta rifiutata dal Risk Gate, Halt, Runtime irraggiungibile), desktop e 390 px; verifica con first-viewport, `impeccable detect`, Playwright, finish review, critique, audit e aggiornamento di `DESIGN.md`. Se i subagenti non rispondono, valutazioni inline secondo le rubric e dillo nel report.

## Dipendenze

Il backend arriva da un'altra sessione (branch `ticker-agents-backend`). Finché non c'è: adattatori tipizzati **con esattamente i nomi del contratto**, stati "non disponibile" che nominano l'endpoint, nessun dato finto in produzione; fixture solo dietro una variabile del dev server (come `COCKPIT_OFFICE_FIXTURES`). In parallelo un'altra sessione costruisce il Portafoglio (branch `portafoglio-frontend`): tocca lo shell solo per aggiungere la rotta e i collegamenti, così l'unione resta semplice.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere sorgenti; `graphify update .` dopo modifiche. Serena per il codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non toccare `runtime/`, `storage/`, `workflows/`, `tools/`, `execution/`, `scripts/`, `config/`.
- Non committare `data/*.db*`, `.serena/`, `frontend/tsconfig.tsbuildinfo`.
- Annota in `.scratch/ticker-agents/wiki-notes-frontend.md` cosa registrare nella wiki e quali adattatori aspettano il backend.
