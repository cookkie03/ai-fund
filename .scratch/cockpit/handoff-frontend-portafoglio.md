# Handoff: pagina Portafoglio del cockpit (Impeccable, code-led)

Repo `/home/luca/trading-agent`, branch di partenza `feat/cockpit-frontend` (shell, Terminale e Ufficio in stile Legend, già uniti). Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: commit sul tuo branch (non su `feat/cockpit-frontend`: l'unione la decide Luca).

## Da leggere prima

`PRODUCT.md`, `docs/frontend.md`, `.scratch/cockpit/brief-portafoglio.md` (brief confermato da Luca), **`.scratch/cockpit/handoff-backend-portafoglio.md` (contratto JSON vincolante)**, `DESIGN.md` e `.impeccable/design.json` (sistema Legend), `docs/dashboard.md`, il codice esistente in `frontend/src/` (shell, Terminale, Ufficio: `features/office/` è il modello per adattatori e fonti oneste).

## Ambiente

PC Linux headless (`192.168.68.107`, utente `luca`); Luca usa un MacBook e vuole l'esperienza Impeccable completa. Pagine Impeccable servite con `IMPECCABLE_QUESTION_FORCE=1`. Porte libere per te: Runtime sintetico **8769** (`uv run python scripts/dev_cockpit_server.py --port 8769 --db data/dev-cockpit-portafoglio-fe.db`), Vite **5178** (`COCKPIT_PORT=5178 COCKPIT_RUNTIME_URL=http://127.0.0.1:8769 npx vite`). Controlla prima con `ss -ltn` che siano libere. Comandi per Luca sul Mac:

```bash
ssh -N -L 5178:127.0.0.1:5178 luca@192.168.68.107
```
```bash
open http://127.0.0.1:5178/portafoglio
```

## Decisioni già prese (non rimetterle in discussione)

- Mode **Operate**, build **code-led**, mondo **Legend**: estendi `DESIGN.md`, nessuna nuova direzione. Riferimenti: informazione professionale prima (IBKR Portfolio Analyst come asticella dei contenuti), sensazione moderna di Revolut e Trade Republic senza la loro povertà di dati; rifinitura Robinhood Legend, macOS Borsa, Linear.
- Struttura: **panoramica in alto + schede** Posizioni, Operazioni, Performance (con attribuzione per posizione, settore, agente), Rischio e vincoli.
- Vincoli di rischio **modificabili subito** con conferma, motivo e storico.
- Azioni: approva/rifiuta ordini, chiudi o riduci posizione, modifica stop e target (con anteprima `dry_run` e conferma), chiedi a un agente (apre `/ufficio/<agente>` sul topic del ticker).
- Grafici: curva equity e benchmark con TradingView lightweight-charts (già nel progetto, stile Legend del Terminale); allocazione con un grafico semplice e leggibile (barre orizzontali con soglia, non torte decorative). Segui la skill `dataviz`.
- Colori finanziari standard per PnL; numeri tabulari; il Risk Gate visibile dove ci sono ordini.

## Flusso Impeccable

1. `.claude/skills/impeccable/scripts/impeccable context --target frontend/src` una volta, poi `reference/new-work.md`; surface brief del Portafoglio con `impeccable surface-brief write`.
2. `reference/craft-floor.md` prima di ogni modifica UI.
3. Costruisci panoramica, schede, azioni, dialoghi di conferma e tutti gli stati del brief, desktop e 390 px.
4. Verifica: first-viewport desktop e 390 px, `impeccable detect`, screenshot Playwright, finish review, `/impeccable critique`, `/impeccable audit`, aggiornamento di `DESIGN.md`. Se i subagenti non rispondono, valutazioni inline secondo le rubric e dillo nel report.

## Dipendenze dal backend

Un'altra sessione implementa endpoint, comandi, eventi e scenario del handoff backend. Finché non arrivano: usa le letture esistenti (`portfolio`, `orders`, `trades`, `equity_history`, `bars`, `approve_order`, `reject_order`) e metti il resto dietro adattatori tipizzati **con esattamente i nomi del contratto** (niente varianti inventate). Dati mancanti → stato "non disponibile" che nomina l'endpoint; nessun dato finto in produzione. Le eventuali fixture di sviluppo solo dietro una variabile d'ambiente del dev server, come `COCKPIT_OFFICE_FIXTURES`.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere sorgenti; `graphify update .` dopo modifiche.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non toccare `runtime/`, `storage/`, `execution/`, `scripts/`, `config/`: lo fa l'altra sessione.
- Non committare `data/*.db*`, `.serena/`, `frontend/tsconfig.tsbuildinfo`.
- Annota in `.scratch/cockpit/wiki-notes-portafoglio-frontend.md` cosa registrare nella wiki e quali adattatori aspettano il backend.
