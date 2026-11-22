# Ufficio: finish review, critique, audit

> ⚠️ DEGRADED: single-context (subagent models unavailable). Sonnet e Haiku hanno risposto `model_not_found`;
> Opus/Fable sono esclusi per regola. Review, critique e audit sono stati fatti nello stesso contesto della build,
> su catture Playwright 1440×900 e 390×844 (Runtime sintetico 8767, Vite 5175 reale e 5176 con fixture).

## Finish review
Disposizione: **ship dopo 2 fix materiali (applicati)**.
- Persistence: il mondo Legend regge su tutte le superfici: tile su desk, niente bordi, raggi a 4 token, colori autore
  solo sui segni dell'autore, verde/rosso mai usati per stato.
- Fidelity al brief: panoramica, vista agente a tre colonne, mobile lista + tab, `say`/`enqueue_task`, costi e token,
  stati onesti. Tutto presente.
- Ceiling: il segno proprio dell'Ufficio è il punto di stato che respira nel colore dell'agente e i blocchi tool che si
  aprono sul posto; abbastanza per una superficie Operate.
- Fix materiali: (1) la conversazione con pochi messaggi galleggiava in alto lasciando un vuoto sopra il composer →
  ancorata in basso come ogni chat; (2) hairline tra Agenti e Chat nella side list (contro "no divider") → spaziatura.
- Keep: StatusMark, seat tile, ToolBlock con payload e nota di compattazione, SourceNote, refusal inline.

## Critique (Nielsen, 0–4)
| Euristica | Voto | Nota |
|---|---|---|
| Visibilità dello stato | 3 | Stato agente, "Dal vivo/Fermo da/Connessione…", tool in corso in cima. Senza heartbeat SSE resta "Connessione…". |
| Corrispondenza col mondo reale | 4 | Metafora ufficio/Slack, italiano naturale, "Con Luca" e `#TICKER`. |
| Controllo e libertà | 3 | Pannelli nascondibili, Esc chiude popover; nessun annulla per `say` (il Runtime non lo prevede). |
| Coerenza e standard | 4 | Stessi tile, seg, scorciatoie e toggle del Terminale. |
| Prevenzione errori | 3 | Ticker validato, Invia disabilitato a vuoto, task con agente esplicito. |
| Riconoscere > ricordare | 4 | Chat con ultima riga e ora, ticker sempre visibile accanto all'agente. |
| Flessibilità ed efficienza | 3 | Invio per inviare, frecce nei radiogroup, deep link `?chat=`. Manca una scorciatoia per cambiare agente. |
| Estetica e minimalismo | 3 | In modalità derived i campi mancanti spariscono invece di dire n/d. Le seat tile hanno un po' di aria in fondo. |
| Errori comprensibili | 4 | Refusal del Runtime verbatim dove è nato; letture fallite con il messaggio. |
| Aiuto e documentazione | 3 | Note di fonte e stati vuoti spiegano cosa manca e quale endpoint lo porterà. |
| **Totale** | **34/40** | |

Assessment B (detector Impeccable sul sorgente): `[]`.
Priorità residue: P2 heartbeat SSE (Runtime/shell); P3 scorciatoia per passare all'agente successivo; P3 altezza
seat tile adattiva quando manca la riga di lavoro.
Questions skipped: sessione avviata da un'altra sessione, decisioni di Luca già fissate nel brief.

## Audit (0–4)
| Dimensione | Voto | Note |
|---|---|---|
| Accessibilità | 3 | Landmark (`nav`, `section` con aria-label), `aria-current`, `aria-expanded`, radiogroup con frecce e roving tabIndex, `aria-live` sulla chat, focus ring. Il punto di stato compatto ha `role="img"` + label. Da verificare con screen reader reale. |
| Performance | 3 | Pagina lazy; orologio da 1 s solo sui tool in corso (altrimenti 60 s); refetch 30 s; query invalidate per evento. La chat legge fino a 500 messaggi senza virtualizzazione. |
| Responsive | 4 | 390 senza scroll orizzontale; lista, selettore chat, tab Chat/Tool; target 32 px su pointer coarse. |
| Theming/token | 4 | Solo token Legend, nessun raggio o colore crudo nuovo; errori in `down` come il resto dello shell. |
| Anti-pattern | 4 | Nessun gradiente, glass, card annidate, numeri finti; fixture solo in dev. |
| **Totale** | **18/20** | |

P0: nessuno. P1: nessuno. P2: virtualizzare la chat se supera qualche centinaio di messaggi; heartbeat SSE.
P3: test screen reader; scorciatoia agente successivo.
