# Note wiki — sessione frontend Opus (shell + Terminale)

Cose che andrebbero aggiornate in wiki (non modificata da questa sessione):

## Backend: difetti/lacune trovati dal frontend
- **SSE `/v1/events`**: gli header HTTP partono solo al primo `yield` (evento o `: ping` dopo 15 s). Un Runtime quieto lascia il browser in "connecting" fino a 15 s. Fix suggerito: `yield ": connected\n\n"` subito all'apertura in `runtime/http.py`. Il cockpit tratta il primo tentativo come "Connessione…" neutro.
- **`OrderDTO`** legge `qty/limit_price/stop_loss` dal draft, ma il draft salva `quantity/entry/stop/take_profit/risk_reward/risk_amount/notional` → nel DTO `qty=0`, `limit_price=None`. Il frontend legge prima `draft_json` (`frontend/src/lib/orders.ts: orderFigures`). Da allineare in `runtime/queries.py`.
- **Approval mode** (manual/auto) non esposto in `/v1/health`: il cockpit non può dire se un ordine aspetta Luca o parte da solo. Suggerito campo `approval_mode` in health.
- **Nessun endpoint quote**: prezzo e variazione della watchlist sono derivati dalle barre 1h (`useWatchBars`). Un `GET /v1/read/quotes?tickers=` eviterebbe N richieste.
- **Nessun registry dei Runtime**: gli account del cockpit vengono da `VITE_COCKPIT_RUNTIMES` (JSON `[{id,label,url}]`), default il proxy locale.
- `approve_order` durante Halt risponde `ok:false, status:"deferred", reasons:["System is halted"]` e l'ordine parte alla ripresa: da documentare (il cockpit disabilita Approva durante Halt).

## Frontend (nuova pagina wiki "Cockpit")
- Stack: React 19, Vite 8, Tailwind 4, shadcn (radix), TanStack Query 5, lightweight-charts 5.3 + lightweight-charts-drawing 0.11, Inter. `frontend/` sostituito per intero (vecchia bozza rimossa).
- Avvio sviluppo: `uv run python scripts/dev_cockpit_server.py --port 8766 --db data/dev-cockpit-opus.db` (riseed a ogni avvio, `--approval-mode manual|auto`), poi `cd frontend && npm run dev` (porta `COCKPIT_PORT`, default 5174; proxy `/v1` → `COCKPIT_RUNTIME_URL`, default `http://127.0.0.1:8766`).
- Scenario dev (`scripts/dev_cockpit_scenario.py`): barre 15m NYSE deterministiche per AAPL NVDA MSFT AMD JPM XOM LLY TSLA GOOGL META AMZN; simboli sconosciuti → nessuna barra (stato "ticker senza dati"). Watchlist con autori misti, annotazioni firmate, ordini in tutti gli stati, trade aperti/chiusi, equity 60 g, inbox. Solo sviluppo: mai in produzione.
- Concetti UI: autore come colore+monogramma (Luca ambra; agenti), "livelli autore" sul grafico (mostra/nasconde/evidenzia i disegni per autore), disegni degli agenti bloccati, quelli di Luca salvati come annotazioni `added_by=cockpit`.
- Freschezza: Live / Connessione… / Dati vecchi (>30 s senza sync o stream in riconnessione) / Runtime irraggiungibile (banner, contenuti desaturati, comandi sospesi).
- Design system: `DESIGN.md` + `.impeccable/design.json` nel repo.
