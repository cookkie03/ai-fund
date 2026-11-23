# Portafoglio backend: note per la wiki

Branch `claude/portafoglio-backend-e1577c`. Contratto: `.scratch/cockpit/handoff-backend-portafoglio.md`;
riferimento API aggiornato in `docs/dashboard.md` §2.5.

## Cosa fa
- **Read model**: `portfolio_summary`, `positions`, `allocation`, `performance`, `attribution`, `risk_limits`,
  `risk_limits_history`; `trades` esteso (`pnl`, `r_multiple`, `duration_s`, `proposed_by`, `stop_price`,
  `target_price`, `qty_remaining`); `equity_history` con `drawdown_fraction`. Query in `runtime/portfolio.py`
  (connessione read-only), metriche pure in `analysis/portfolio_metrics.py`.
- **Limiti Risk Gate versionati** (`execution/risk_limits.py`, tabella `risk_limits_versions`, migrazione 7):
  `office.toml` resta la versione 0 virtuale; ogni modifica dal cockpit è una nuova versione con attore, motivo,
  prima/dopo, voce in Inbox ed evento `risk_limits.updated`. `Office.build_risk_gate_context` e il ciclo leggono la
  versione attiva a ogni valutazione (nessun riavvio). I motivi del Risk Gate citano la soglia reale.
- **Comandi**: `update_risk_limits`, `close_position`, `modify_exit` (+ `dry_run`). `execution/position_exits.py`
  (`PositionExits`) gestisce anteprima, Halt, Risk Gate e broker; `ClosePosition`/`ModifyExit` sono comandi "di rete"
  (handler fuori transazione, come `ApproveOrder`); `dry_run` non scrive e non emette eventi di comando.
- **Trade**: colonne nuove `stop_price`, `target_price`, `initial_stop`, `proposed_by`, `closed_qty`,
  `realized_pnl` (chiusure parziali: quantità residua = `qty - closed_qty`). `proposed_by` si fissa all'ingresso dallo
  stato del ticker (suggerimento `buy` con convinzione massima, altrimenti la decisione del PM).
- **Eventi** (pubblicati solo al commit): `portfolio.updated`, `position.changed` (`opened|reduced|closed|exit_levels|
  trailing_stop`), `risk_limits.updated`, nuovo `trade.reduced`; `reconcile_broker` emette anche `portfolio.updated`.

## Scelte da ricordare
- Bounds: rischio per trade 0,1–5%, posizione 1–25%, settore 5–60%, posizioni aperte 1–100, riserva di cassa 0–50%,
  R:R minimo 1–10, embargo utili 0–10 giorni. Fuori range = `ok:false` con un motivo per violazione.
- Uscita manuale = `exit_reason: pm_sell`. Il fill di una vendita manuale già nota alla chiusura (broker finto) non viene
  riapplicato dallo stream (`exit_recorded` sull'ordine); con broker reale il fill arriva dallo stream e le vendite
  locali sono `pm_sell` (quantità < residua = chiusura parziale).
- `modify_exit`: stringere lo stop è sempre ok (anche in Halt); allargarlo passa dal solo controllo rischio per trade
  del Risk Gate. Ordine protettivo modificato con `modify_stop`/`modify_take_profit` del broker.
- Portafoglio vuoto: `portfolio_summary` a zero con `ts` null. Metriche con pochi dati: `null` + `insufficient`.
- `usage` dei limiti non include l'embargo utili.
- **Non verificato su broker reale**: `AlpacaBracketAdapter.close_position` (cancella le gambe, vendita market/limit,
  OCO sul residuo) è provato solo con un client finto; serve una prova su paper account.
- Scenario di sviluppo (`scripts/dev_cockpit_scenario.py`): 6 posizioni su 4 settori (Technology ~27% su limite 32%),
  ~26 trade chiusi, equity oltre un anno correlata a SPY, una modifica ai limiti, broker finto che esegue
  `close_position`/`modify_exit`. Smoke HTTP/SSE reale su porta 8770.
