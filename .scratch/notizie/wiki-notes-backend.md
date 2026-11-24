# Wiki Notes: Ambiente Notizie e Calendario (Backend)

## Sintesi delle modifiche introdotte
- **Tabelle aggiunte**:
  - `news_sources`: gestione delle fonti (Alpaca, RSS, OpenBB) con stato (`ok`, `error`, `unavailable`), abilitazione e timestamp di ultimo fetch.
  - `news`: estesa con `url`, `source_id`, `provider`, `published_ts`, `fetched_ts`, `tickers_json`, `themes_json`, `image_url`, `has_full_text`.
  - `news_usage`: traccia d'uso granulare per notizia (`read` dai tool agenti, `cited` nelle citazioni/dossier, `forwarded` per gli inoltri di Luca).
  - `calendar_events`: calendario unificato macro ed earnings con importanza, data/ora, actual, forecast, previous.
- **Provider & Ingestion**:
  - Ingestione periodica come job del Runtime (`NewsIngestionJob`, ogni 15 min).
  - Parser RSS/Atom robusto basato su `httpx` e `xml.etree.ElementTree` (timeout, limite dimensione, solo http/s).
  - Adapter OpenBB integrato con gestione di indisponibilità (`unavailable`).
  - Paginazione Alpaca oltre le 50 notizie.
- **Agent Tools**:
  - `news_by_ticker`, `news_by_theme`, `news_search`, `economic_calendar`, `earnings_calendar`.
  - Registrati per PM, Market, Fundamental, Sentiment, Technical, Risk.
- **Comandi per Luca**:
  - `forward_news`, `add_news_source`, `set_news_source_enabled`, `remove_news_source`, `refresh_news` con supporto Idempotency-Key e X-Actor.
- **Eventi SSE**:
  - `news.ingested`, `news.used`, `news.source`.

## Sezioni da registrare nella Wiki
- `system/interface/frontend-module.md`: inserire i contratti di lettura (`/v1/read/news`, `/v1/read/news_item`, `/v1/read/news_sources`, `/v1/read/calendar`) e i comandi per la gestione delle fonti e l'inoltro delle notizie.
- `system/foundation/database-schema.md`: documentare le tabelle `news_sources`, `news`, `news_usage`, `calendar_events` e la migrazione 009.
