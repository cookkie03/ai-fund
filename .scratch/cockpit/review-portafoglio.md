# Portafoglio: finish review, critique, audit

> ⚠️ DEGRADED: single-context (subagent models unavailable). Sonnet e Haiku hanno risposto `model_not_found` (404);
> Opus/Fable sono esclusi per regola. Review, critique e audit sono stati fatti nello stesso contesto della build, su
> catture Playwright 1440×900 e 390×844: fixture dev (Vite 5178, Runtime sintetico 8769) e Runtime reale del branch
> backend (`scripts/dev_cockpit_server.py` su 8772, Vite 5179 senza fixture).

## Verifiche eseguite
- `impeccable first-viewport` desktop e 390: tesi (`[data-region="summary"]`) al 100% nel primo viewport, tab al fold
  e cliccabili, nessun vuoto oltre 45 px. Cifre passate con `--figures-supplied`: vengono dal Runtime; in modalità
  fixture la testata porta il tag **Dati di esempio**.
- `impeccable detect` su `frontend/src/pages/portafoglio` e `index.css`: 0 findings.
- Playwright, sia su fixture sia sul backend reale: toggle SPY (`aria-pressed`), periodo, chiusura parziale 50% con
  anteprima dry-run e invio (JPM 35 → 17 sul backend), modifica stop con anteprima, tre tab con click reale, modifica
  vincoli (valore, motivo, Rivedi, Conferma: nuova versione nello storico), bottom sheet mobile, tab Rischio e
  Performance a 390. Zero errori in console, 0 px di overflow orizzontale a 390.

## Finish review
Disposizione: **ship dopo 5 fix materiali (applicati)**.
- Persistence: mondo Legend intatto. Tile su desk senza bordi, raggi a 4 token, up/down solo per P&L, warn = vicino,
  down = sforato, azzurro solo sull'azione che impegna capitale (Vendi N azioni, Applica, Conferma e applica).
- Fidelity al contratto: panoramica (equity, oggi, PnL, investito/cassa, curva con periodi e SPY indicizzato, drawdown
  in pannello proprio, allocazione a barre con soglia), quattro tab, azioni con dry-run e conferma, vincoli con motivo
  e storico, 390 px. Tutto presente.
- Ceiling: il segno proprio è la **tacca di soglia**: ogni esposizione è disegnata contro il suo limite, e nella
  revisione dei vincoli la tacca si sposta sopra l'uso attuale mostrando il cambio di stato prima di confermare.
- Fix materiali: (1) i nomi dei campi delle anteprime dry-run non combaciavano con il backend (`reference_price`,
  `estimated_value`, `estimated_realized_pnl`, `qty_remaining_after`, `previous_stop_price`, `risk_gate.allowed`) →
  normalizzatori e fixture allineati, verificato sul backend reale; (2) top bar e pagina mostravano equity diverse in
  modalità fixture → la fixture risponde anche a `portfolio`; (3) variazione di oggi calcolata sul giorno UTC → giorno
  di New York come la top bar; (4) etichette dei due pannelli del grafico sovrapposte → margini e stretch del pannello
  drawdown; (5) le tab Radix non rispondevano a un `click()` senza mousedown (tecnologie assistive) → il click mette a
  fuoco il trigger e l'attivazione automatica seleziona (`components/panel-tabs.tsx`, vale per tutto il cockpit).

## Critique (Nielsen, 0–4)
| Euristica | Voto | Nota |
|---|---|---|
| Visibilità dello stato | 4 | Freschezza dello snapshot con età in warn, stream broker, Halt in banner, "ora fa" nello storico. |
| Corrispondenza col mondo reale | 4 | Lessico da estratto conto (Investito, Cassa, Rischio aperto), italiano naturale, giorno di borsa NY. |
| Controllo e libertà | 3 | Ogni azione di capitale ha anteprima, Annulla e Indietro; nessun annulla dopo l'invio (il broker non lo prevede). |
| Coerenza e standard | 4 | Stessi tile, seg, dialoghi Approva/Rifiuta riusati dal Terminale. |
| Prevenzione errori | 4 | Dry-run prima del primario, limiti con bound, motivo obbligatorio, Rivedi con prima → dopo. |
| Riconoscere > ricordare | 4 | Ogni cifra porta il suo termine di paragone (soglia, riserva, max posizioni). |
| Flessibilità ed efficienza | 3 | Quick pick 25/50/75%, tabella ordinabile, tab ricordata. Manca una scorciatoia da tastiera per le tab. |
| Estetica e minimalismo | 4 | Una sola cifra grande, niente torta, colore solo dove c'è uno stato. |
| Errori comprensibili | 4 | Motivi del Risk Gate verbatim nel dialogo, endpoint mancante nominato negli stati non disponibili. |
| Aiuto e documentazione | 3 | Hint su ogni metrica e vincolo; le metriche insufficienti dicono quante osservazioni servono. |

Top issue di design residue (non bloccanti):
1. In SPY la linea del portafoglio resta rossa se il periodo è negativo anche quando batte SPY: è la regola (colore =
   direzione), il confronto sta nella legenda "(+1,12% vs SPY)".
2. La tile Allocazione a 1440 ha aria in fondo quando i settori sono pochi.
3. Il nome account troncato nella top bar a 390 è della shell, non di questa pagina.

## Audit
| P | Dove | Problema | Stato |
|---|---|---|---|
| P1 | `features/portfolio/api.ts` normalizzatori | Nomi dell'anteprima diversi dal backend: l'anteprima sarebbe stata vuota e il gate sempre "ok". | Corretto |
| P1 | `components/panel-tabs.tsx` | Tab non attivabili con un click senza mousedown. | Corretto |
| P2 | `pages/portafoglio/equity-chart.tsx` | Il canvas non aveva alternativa testuale. | `role="img"` con riepilogo (valore, rendimento, SPY, drawdown max) |
| P2 | `equity-chart.tsx` | Ogni refetch live (`portfolio.updated`) distruggeva e ricreava il grafico, perdendo il crosshair. | Creazione separata da `setData` |
| P2 | `features/portfolio/api.ts` `fetchSummary` | Portafoglio mai sincronizzato (`ts: null`) mostrato come $0. | Ora "Nessuno snapshot" |
| P3 | `position-actions.tsx` | Valori iniziali di stop/target/limite col punto decimale, il resto della UI con la virgola. | Corretto |
| P3 | `position-actions.tsx` | In Halt anche stringere lo stop è bloccato; il backend lo permette. | Aperto (follow-up) |

Contrasto: testo secondario in `fg-subtle` sui ground come nel resto del cockpit; nessun testo in `fg-faint`. Segnali
mai solo colore: stato con icona e parola, P&L con segno.
