# Notizie — note frontend per la wiki

Branch: `claude/notizie-frontend-ui-a38556` (da `notizie-frontend`). Solo `frontend/`, `DESIGN.md`, queste note.

## Cosa c'è

- **`/notizie`** (`frontend/src/pages/notizie/`): Flusso filtrabile dal vivo + Lettore (Notizia | Calendario) su desktop; su telefono tab Flusso/Calendario, filtri in un foglio dal basso, lettore come pagina spinta con indietro.
- **Filtri in URL**: `scope` (all|portfolio|watchlist), `ticker`, `theme`, `source_id`, `provider`, `q`, `id` (notizia selezionata). `/notizie?ticker=SYM` è il deep link usato da Scheda del ticker (header, "Notizie su SYM") e Terminale (icona giornale accanto al simbolo).
- **Flusso**: infinite scroll a cursore (`next_before`), intestazioni di giorno, ↑/↓ e j/k, segni d'uso (letture/citazioni/inoltri) per riga. Le notizie nuove non spostano la lettura: aspettano dietro "N nuove notizie".
- **Lettore**: meta, titolo, ticker (link a scheda e grafico), **Inoltra**, "Apri su host", corpo onesto (testo pieno / solo sommario / solo titolo), traccia d'uso con link a ciclo e chat.
- **Inoltro**: Inoltra apre un menu (Agenti del ticker, poi Ufficio). La scelta apre `/ufficio/<agente>?chat=…&news=ID[&fwd=SYM]` con la notizia allegata al composer; la nota è il messaggio (obbligatoria) e Invia manda `forward_news`. Ticker senza agente → Portfolio Manager. Modifiche in `pages/ufficio/conversation.tsx` (Composer).
- **Calendario**: macro + trimestrali 7 giorni, filtro Tutti/Macro/Trimestrali, barre di importanza, eventi su posizioni e watchlist in evidenza.
- **Fonti**: foglio laterale con stato per fonte (Attiva / Errore verbatim / Disattivata / Non disponibile), interruttore, Aggiorna, Rimuovi in due passi (RSS), Aggiorna tutte, aggiunta feed RSS/Atom con validazione http(s).
- **Live**: SSE `news.ingested` (invalida testa e fonti), `news.used` (aggiorna i conteggi in place e invalida il dettaglio), `news.source` (invalida fonti).

## Adapter in attesa del backend

Tutti in `frontend/src/features/news/api.ts` + `lib/runtime/types.ts`, nomi esatti di `handoff-backend.md`. Finché il Runtime risponde 404 ("Read endpoint 'x' not found" / "Command 'x' not found") la UI mostra uno stato "non ancora esposto" che nomina l'endpoint.

| Tipo | Endpoint | Dove si vede |
|---|---|---|
| read | `GET /v1/read/news` (filtri + `before`, `limit`) | Flusso |
| read | `GET /v1/read/news_item?id=` | Lettore + traccia d'uso |
| read | `GET /v1/read/news_sources` | Fonti, conteggio problemi, opzioni filtro Fonte |
| read | `GET /v1/read/calendar?from&to[&kind]` | Calendario + badge 48 h |
| command | `forward_news {news_id, to:{agent}|{ticker}, note}` | Composer Ufficio |
| command | `add_news_source {provider:"rss", name, url}` | Fonti |
| command | `set_news_source_enabled {source_id, enabled}` | Fonti |
| command | `remove_news_source {source_id}` | Fonti |
| command | `refresh_news {source_id \| null}` | Fonti |
| SSE | `news.ingested`, `news.used`, `news.source` | invalidazioni live |

Comandi con `Idempotency-Key` e `X-Actor` come gli altri; i rifiuti (`ok:false, reasons`) sono mostrati verbatim dove nascono.

## Fixture di sviluppo

`COCKPIT_NEWS_FIXTURES=1` (solo dev server Vite, `frontend/dev/news-fixtures.ts`): 84 notizie sintetiche, 5 fonti, calendario della settimana, ingest ogni 25 s e `news.used` 9 s dopo via `/v1/dev/news-events`. Header con tag **Dati di esempio**. Cookie `news_fixture` per gli stati: `empty`, `nocal`, `missing` (404 su tutto), `down` (502), `refuse` (comandi rifiutati). Assenti dalla build di produzione.

## Design

Sezioni nuove in `DESIGN.md`: Notizie layout, Wire row, Usage mark, Usage trace, Forward menu and news attachment, Body honesty, Calendar row, Sources sheet. Brief di superficie: `.impeccable/surfaces/frontend-src-pages-notizie.md`.
