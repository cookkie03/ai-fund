# Trading Agent

Un "ufficio di agenti di trading" per azioni USA: sei agenti pari (Portfolio Manager, Market, Sentiment, Technical, Fundamental e Risk Analyst) ragionano tramite messaggi in chat, ciascuno richiamato da uno Scheduled task. Gli LLM propongono e discutono; bozza dell'ordine, Risk Gate, trailing stop ed esecuzione sono calcoli deterministici testati. Il broker è Alpaca **paper**; la spec è in [`.scratch/agent-mvp/spec.md`](.scratch/agent-mvp/spec.md).

Flusso di un ciclo su un ticker: Scheduled task → il PM scrive ai quattro Analyst → gli Analyst rispondono (e il Risk Analyst calibra `k_entry`/`risk_fraction`) → il codice calcola la bozza dell'ordine → il PM la accetta o rimanda (`defer`) → il Risk Gate può solo bloccare → ordine bracket (limit + take profit + stop) su Alpaca, in automatico o dopo approvazione manuale. Ogni decisione programma un controllo futuro.

## Requisiti

- Python 3.12 e [`uv`](https://docs.astral.sh/uv/); Docker con Compose per la produzione.
- Un endpoint LLM compatibile OpenAI (di default OmniRoute su `http://localhost:20128/v1`, modello `my-combo`).
- Un conto Alpaca paper (chiave e secret).

## Configurazione

I segreti stanno solo nel file `.env` (mai committato, mai nel TOML):

| Variabile | Uso |
|---|---|
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Obbligatorie: broker, portafoglio e news Alpaca. |
| `ALPACA_TRADING_URL` | Facoltativa; default `https://paper-api.alpaca.markets/v2`. |
| `OMNIROUTE_API_KEY` | Chiave dell'endpoint LLM (nome indicato da `api_key_env` per ogni agente). |
| `OFFICE_LLM_ENDPOINT` | Facoltativa: sovrascrive l'endpoint di tutti gli agenti (usata da Docker). |
| `DATA_PRICES_PROVIDER` | `yahoo` (default) o `openbb`; se uno non parte, si usa l'altro. |
| `TRADING_AGENT_DB` | Percorso del DB SQLite; default `data/trading-agent.db`. |

Le impostazioni non segrete sono in [`config/office.toml`](config/office.toml):

- `approval_mode`: `"auto"` invia subito l'ordine al broker, `"manual"` lo mette in coda finché non lo approvi con `orders approve`. **Per le prime prove usa `manual`.**
- `max_parallel`, `[budgets]` (limiti di messaggi per ciclo), `[schedule]` (orari NY), `[retention]` (conservazione dati) e `db_size_alert_mb`.
- `[limits]`: i limiti del Risk Gate (rischio per trade 1%, posizione 10%, settore 30%, cassa minima 5%, R:R minimo 1,5, embargo utili 2 giorni).
- `[agents.*]`: endpoint, modello, `effort` e `api_key_env` di ciascun agente.

Controlla configurazione e credenziali con `uv run trading-agent config check`.

I prompt degli agenti sono in [`prompts/`](prompts/) (un file Markdown per agente, versionato; l'hash finisce nel registro di ogni chiamata LLM). Sono bozze marcate "DRAFT per la revisione di Luca": rileggili e correggili.

## Uso in locale

```bash
uv sync
uv run trading-agent config check # verifica configurazione (comando locale)
uv run trading-agent run          # avvia il Runtime single-writer (scheduler event-driven + API HTTP/SSE su :8765)
```

In un altro terminale (i comandi CLI operano come client sottile via HTTP contro il Runtime):

```bash
uv run trading-agent task AAPL --reason "Valuta un ingresso long"   # accoda un ciclo manuale
uv run trading-agent cycles list                # cicli e loro esito
uv run trading-agent chat show portfolio_manager AAPL    # conversazione del PM sul ticker
uv run trading-agent state show AAPL            # stato condiviso (analisi, coefficienti, bozza)
uv run trading-agent orders list                # ordini e stato
uv run trading-agent orders approve <id>        # con approval_mode = "manual"
uv run trading-agent orders reject <id>
uv run trading-agent orders sync                # allinea gli ordini allo stato del broker
uv run trading-agent trades list                # trade aperti/chiusi (trailing stop)
uv run trading-agent portfolio sync             # equity, cassa, posizioni da Alpaca
uv run trading-agent watchlist --help           # gestione della watchlist
uv run trading-agent inbox                      # avvisi: rischio, budget, errori, dimensione DB
uv run trading-agent say portfolio_manager AAPL "testo"   # scrivi tu a un agente
uv run trading-agent halt                       # ferma tutto e cancella gli ordini aperti
uv run trading-agent resume
```

Ogni sottocomando ha `--help`.

## Produzione con Docker

```bash
docker compose -f compose.engine.yaml up -d --build
docker compose -f compose.engine.yaml logs -f engine
```

Il servizio `engine` legge `.env`, tiene il DB nel volume `trading-agent-data` e si unisce alla rete Docker `omniroute_default` per raggiungere OmniRoute (`OFFICE_LLM_ENDPOINT`). Per usare la CLI dentro il container:

```bash
docker compose -f compose.engine.yaml exec -T engine uv run --no-sync trading-agent <comando>
```

## Test

```bash
uv run pytest -q                                                       # suite offline (broker, LLM e dati finti)
uv run pytest tests/integration/test_office_smoke.py --alpaca-paper -m integration -q -s   # opt-in: LLM veri, broker finto
```

Lo smoke test richiede `OMNIROUTE_API_KEY` e legge dati live con `OFFICE_SMOKE_LIVE_DATA=1`. Lint: `uv run ruff check execution tools workflows storage bootstrap.py interface agents data analysis`.

## Struttura

| Cartella | Contenuto |
|---|---|
| `workflows/` | Motore (`Office`), ciclo (`CycleRunner`), scheduling, calendario di mercato |
| `agents/` | Backend LLM sostituibile (OpenAI-compatibile) e backend finto per i test |
| `tools/` | Ambiente degli agenti: tool per ruolo, schemi Pydantic |
| `execution/` | Bozza dell'ordine, Risk Gate, flusso ordini, trade manager, trailing |
| `storage/` | DB SQLite (WAL), registro LLM/tool, retention |
| `data/` | Cache dati DB-first e provider (Yahoo, Alpaca news, OpenBB) |
| `analysis/` | Indicatori tecnici (SMA, EMA, RSI, MACD, ATR, pivot) |
| `interface/` | CLI `trading-agent` |
| `config/` | Impostazioni (`office.toml`) |
| `prompts/` | System prompt degli agenti |
| `docs/` | [Architettura](docs/architecture.md) e ricerca |

`frontend/`, `openbb-ui/` e `telegram-claude/` sono app separate non collegate al motore.

## Avvertenze

- È un sistema sperimentale collegato a un conto **paper**. Nessuna informazione paper/live è esposta agli agenti, ma non collegarlo a un conto reale senza una revisione dei prompt e dei limiti del Risk Gate.
- Gli LLM possono sbagliare: il Risk Gate blocca solo ciò che viola i limiti numerici, non valuta la qualità della tesi.
- Ogni ciclo reale consuma token dell'endpoint LLM (tipicamente 30 s – 4 min per ticker).
