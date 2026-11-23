# Portafoglio frontend: note per la wiki

Branch `claude/portafoglio-frontend-06bcf6`. Contratto: `.scratch/cockpit/handoff-backend-portafoglio.md`; direzione:
`.scratch/cockpit/surface-brief-portafoglio.md`; review: `.scratch/cockpit/review-portafoglio.md`.

## Cosa c'è
- Pagina `/portafoglio` (`frontend/src/pages/portafoglio/`): testata con conto e freschezza, banda di riepilogo, curva
  dell'equity (lightweight-charts, periodi 1G–Tutto, SPY indicizzato a 0%, drawdown in pannello proprio), allocazione a
  barre con tacca di soglia, poi tab Posizioni, Operazioni, Performance (metriche + attribuzione per posizione, settore,
  agente), Rischio e vincoli (uso attuale, modifica con motivo e revisione, storico). Mobile 390: riepilogo compatto,
  curva 220 px, lista posizioni con bottom sheet, allocazione dentro la tab Rischio.
- Dati in `frontend/src/features/portfolio/` (`types.ts` con i nomi esatti del contratto, `api.ts` adapter,
  `hooks.ts` TanStack Query con chiavi `["pf", …]`). Eventi SSE in `lib/runtime/provider.tsx`: `portfolio.updated`,
  `position.changed`, `risk_limits.updated` invalidano le chiavi `pf`.

## Adapter: endpoint del backend e ripiego
Ogni adapter prova l'endpoint; se il Runtime risponde 404 "not found" ripiega e lo dice nella nota di fonte.
| Lettura/comando | Senza endpoint |
|---|---|
| `portfolio_summary` | Ricostruito da `portfolio`, `equity_history`, `trades` (giorno di borsa NY). |
| `positions` | Da `portfolio` + `orders`; settore e agente n/d. |
| `allocation` | Per posizione con i limiti di default; per settore non disponibile. |
| `performance` | Rendimento e drawdown dalla curva, statistiche trade dai trade; vol/Sharpe/Sortino n/d. |
| `attribution` | Solo per posizione. |
| `risk_limits` | Limiti di default + uso derivato; modifica disabilitata. |
| `risk_limits_history` | Non disponibile, con il nome dell'endpoint. |
| `close_position`, `modify_exit`, `update_risk_limits` | Banner "comando non ancora esposto"; primario disabilitato. |

Verificato end-to-end sul branch `claude/portafoglio-backend-e1577c` (dev server su 8772): tutte le letture e i tre
comandi rispondono 200 e la pagina non usa nessun ripiego.

## Da ricordare
- **Anteprime dry-run**: i nomi sono quelli del backend (`reference_price`, `estimated_value`,
  `estimated_realized_pnl`, `qty_remaining_after`, `previous_stop_price`, `previous_target_price`,
  `risk_gate: {allowed, reasons}`); il frontend li normalizza nei suoi tipi interni.
- Il frontend manda `confirm: true` anche con `dry_run: true`: il backend lo accetta (richiede confirm solo senza
  dry_run).
- `portfolio_summary` con `ts: null` = conto mai sincronizzato: la pagina mostra "Nessuno snapshot", non $0.
- Fixture dev: `COCKPIT_PORTFOLIO_FIXTURES=1` (solo `vite serve`) risponde a letture e comandi con stato mutabile e mette
  il tag **Dati di esempio** in testata. In build non esistono.
- `components/panel-tabs.tsx`: il click mette a fuoco il trigger, così le tab rispondono anche a un click senza
  mousedown (tecnologie assistive). Vale per tutte le tab del cockpit.

## Aperto
- In Halt anche stringere lo stop è bloccato nella UI; il backend lo permette (riduce il rischio). Da sbloccare solo per
  stop più stretto.
- `AlpacaBracketAdapter.close_position` provato solo con broker finto (nota del backend).

## Avvio
```bash
# fixture (nessun backend Portafoglio necessario)
COCKPIT_RUNTIME_URL=http://127.0.0.1:8769 COCKPIT_PORT=5178 COCKPIT_PORTFOLIO_FIXTURES=1 npx vite
# senza fixture, contro un Runtime con il backend Portafoglio
COCKPIT_RUNTIME_URL=http://127.0.0.1:8766 COCKPIT_PORT=5178 npx vite
```
