# Handoff: backend del Runtime per il Portafoglio del cockpit

Repo `/home/luca/trading-agent`, branch di partenza `feat/cockpit-frontend`. Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: test verdi, ruff pulito, `graphify update .`, commit e push sul tuo branch (non su `feat/cockpit-frontend`: l'unione la decide Luca).

## Perché

Prossima pagina: il Portafoglio (`.scratch/cockpit/brief-portafoglio.md`, confermato da Luca). Serve un read model professionale del portafoglio, metriche e attribuzione, vincoli di rischio **modificabili subito**, e tre azioni di capitale nuove. API attuale: `docs/dashboard.md`. Architettura single-writer: `docs/adr/0003-runtime-unico-writer-event-driven.md`. Esistono già `/v1/read/portfolio`, `orders`, `trades`, `equity_history`, `bars`, i comandi `approve_order`/`reject_order`, il Risk Gate (`execution/risk_gate.py`, limiti da `[limits]` di `config/office.toml` via `config/office_settings.py`), il flusso ordini (`execution/order_flow.py`, `execution/trade_manager.py`, `brokers/alpaca_orders.py`).

## Contratto (vincolante: il frontend usa esattamente questi nomi)

Nell'Ufficio frontend e backend avevano nomi di campo diversi: qui il contratto è fissato. Se devi cambiarlo, aggiorna questo file e `docs/dashboard.md` nello stesso commit e scrivilo nel report. Importi in valuta del conto come numeri, percentuali come frazioni (`0.12` = 12%), timestamp ISO UTC.

1. `GET /v1/read/portfolio_summary` →
   `{ts, equity, cash, invested, cash_reserve_fraction, day_change, day_change_fraction, unrealized_pnl, realized_pnl_today, positions_count, snapshot_age_s, halted}`
2. `GET /v1/read/positions` → lista di
   `{ticker, side, qty, avg_entry_price, current_price, market_value, weight, unrealized_pnl, unrealized_pnl_fraction, stop_price, target_price, open_risk, open_risk_fraction, sector, opened_ts, days_held, trade_id, proposed_by}`
   `open_risk` = perdita fino allo stop; `proposed_by` = agente che ha proposto il trade (dal ciclo o dalla bozza d'ordine), `null` se ignoto.
3. `GET /v1/read/allocation` → `{by_sector: [{sector, value, weight, limit}], by_position: [{ticker, value, weight, limit}], cash: {value, weight, min_reserve}}`
4. `GET /v1/read/performance?period=1D|1W|1M|3M|YTD|1Y|ALL&benchmark=SPY` →
   `{period, from, to, observations, return_fraction, realized_pnl, unrealized_pnl, max_drawdown_fraction, current_drawdown_fraction, volatility_annualized, sharpe, sortino, win_rate, profit_factor, expectancy, expectancy_r, trades_closed, benchmark: {ticker, return_fraction, beta, correlation} | null, insufficient: [{metric, reason, min_observations}]}`
   Una metrica che non ha abbastanza dati vale `null` e compare in `insufficient` con il motivo: mai un numero calcolato su 3 punti. Benchmark dalle barre giornaliere già disponibili nel Runtime; se mancano, `benchmark: null`. Risk-free a 0 salvo configurazione esplicita; documenta le formule in `docs/dashboard.md`.
5. `GET /v1/read/attribution?period=` → `{by_position: [{ticker, pnl, contribution_fraction}], by_sector: [{sector, pnl, contribution_fraction}], by_agent: [{agent, pnl, contribution_fraction, trades}]}`
6. `GET /v1/read/trades` esistente: aggiungi se mancano `r_multiple`, `duration_s`, `pnl`, `proposed_by`, `exit_reason` (non rompere i campi attuali).
7. `GET /v1/read/risk_limits` →
   `{version, updated_ts, updated_by, limits: {max_risk_per_trade_fraction, max_position_fraction, max_sector_fraction, max_open_positions, min_cash_reserve_fraction, min_risk_reward_ratio, earnings_embargo_days}, bounds: {<nome>: {min, max}}, usage: [{limit, current, threshold, status: "ok"|"near"|"breach", detail}]}`
   `usage` mostra l'utilizzo attuale di ogni limite (es. settore più esposto 0.22 su 0.30); `near` sopra l'80% della soglia.
8. `GET /v1/read/risk_limits_history?limit=` → `[{version, ts, actor, reason, before, after}]`
9. `equity_history` esistente: verifica che basti per curva e drawdown su tutti i periodi; aggiungi `drawdown_fraction` per punto se manca.

## Comandi (con `Idempotency-Key`, `X-Actor`, `confirm:true`, risposta `{ok, data, reasons}`)

- `update_risk_limits {limits: {...parziale}, reason}`: persistenza nel DB (tabella versionata con attore, motivo, prima e dopo), `config/office.toml` resta il default iniziale. Ogni valore deve stare nei `bounds` (definiscili tu, prudenti: es. rischio per trade fino al 5%, riserva di cassa almeno 0%, R:R almeno 1.0); fuori range → `ok:false` con motivo. **Il Risk Gate legge la versione attiva a ogni valutazione**, non una copia presa all'avvio. Le posizioni esistenti non vengono toccate: lo sforamento compare in `usage`. Voce nell'Inbox per ogni modifica.
- `close_position {ticker, qty | null, order_type: "market"|"limit", limit_price | null}`: chiusura totale (`qty:null`) o parziale. Passa dal flusso ordini esistente (come `pm_sell`), idempotente, bloccato in Halt; aggiorna il trade e lo stop residuo sulla quantità rimasta. `data` include l'ordine creato.
- `modify_exit {ticker, stop_price | null, target_price | null}`: sposta stop e/o target. Stringere lo stop è sempre ammesso; allontanarlo ricalcola il rischio aperto e passa dal controllo rischio per trade del Risk Gate (`reasons` con le regole violate). Usa il percorso di sostituzione degli ordini protettivi di `trade_manager`.
- Anteprima senza effetti: un parametro `dry_run:true` su `close_position` e `modify_exit` restituisce quantità, valore stimato, PnL che si realizza o nuovo rischio, ed esito del Risk Gate, senza scrivere nulla.

## Eventi SSE (nella tabella `events`, dal punto di scrittura reale, niente polling)

`portfolio.updated` (nuovo snapshot), `position.changed` (apertura, chiusura, riduzione, nuovo stop/target), `risk_limits.updated`. Verifica che `order.*` e `trade.*` esistenti coprano il resto.

## Scenario di sviluppo

Estendi `scripts/dev_cockpit_scenario.py` / `dev_cockpit_server.py`: almeno 6–10 posizioni su 3–4 settori (una vicina al limite di settore), stop e target, uno storico di trade chiusi lungo abbastanza per tutte le metriche (vinti, persi, motivi di uscita diversi, agenti proponenti diversi), equity history di almeno un anno, barre giornaliere SPY, ordini in attesa di approvazione, una modifica dei vincoli nello storico. Il broker finto deve eseguire `close_position` e `modify_exit` così il frontend può provarli. Mai usato in produzione.

## Verifica

Test-first (skill `tdd`): formule delle metriche su serie note, casi `insufficient`, bounds e versioning dei limiti, Risk Gate che legge i limiti nuovi, `modify_exit` che stringe (ok) e allarga oltre il rischio (rifiutato), `close_position` parziale e in Halt, eventi pubblicati solo al commit. Poi smoke HTTP/SSE reale sul server di sviluppo sulla porta **8770** (`--db data/dev-cockpit-portafoglio-be.db`). Aggiorna `docs/dashboard.md`.

## Fuori scope

`frontend/`, Bridge, Evaluation completa, report fiscali, multi-valuta, CORS.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere i sorgenti. Serena per il codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non committare `data/*.db*`, `nohup.out`, `.serena/`, `graphify-out/` (salvo il grafo se già tracciato), `frontend/tsconfig.tsbuildinfo`.
- Un'altra sessione costruisce in parallelo la pagina in `frontend/`: non toccarlo. Annota in `.scratch/cockpit/wiki-notes-portafoglio-backend.md` cosa registrare nella wiki (la wiki la scrive la sessione principale).
