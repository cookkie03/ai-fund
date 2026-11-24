# Handoff: ambiente Notizie del Runtime (backend)

Repo `/home/luca/trading-agent`, branch **`notizie-frontend`** (la branch della pagina, già creata da `main` e pushata). Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: test verdi, ruff pulito, `graphify update .`, commit e push su `notizie-frontend`. Non aprire la PR e non unire su `main`: lo fa la sessione principale dopo il frontend.

**Quando partire e dove:** il backend del Bridge (branch `assistente-frontend`) tocca gli stessi file del Runtime (`runtime/commands.py`, `runtime/queries.py`, `runtime/core.py`, `storage/office_db.py`, scenario di sviluppo). Se `assistente-frontend` è già unito su `main`, porta `notizie-frontend` su `main` aggiornato (`git merge origin/main`) prima di iniziare. Altrimenti lavora comunque, ma tieni le modifiche a quei file piccole e localizzate e segnala nel report i punti di possibile conflitto. Se il checkout principale è occupato da un'altra sessione, lavora in un worktree tuo su `notizie-frontend`. Non toccare `frontend/`: lo fa un'altra sessione in parallelo, con il contratto qui sotto.

## Obiettivo

Rendere le notizie un **ambiente del Runtime** condiviso da agenti e cockpit (leggi `.scratch/notizie/brief.md` per primo): ingestione da tutte le fonti in SQLite, letture per la pagina, tool degli agenti che leggono dallo stesso archivio, traccia d'uso per notizia, inoltro di Luca agli agenti, calendario macro ed earnings.

## Da leggere

- Wiki (`/home/luca/trading-agent-wiki/wiki/`): `system/interface/frontend-module.md`, `system/foundation/decision-log.md`, pagine sulle fonti dati e sul Sentiment Analyst (`grep -ril news wiki/system`).
- Repo: `AGENTS.md`, `docs/architecture.md` («News e desk sentiment — 2026-11-02»), `docs/adr/0003-runtime-unico-writer-event-driven.md`, `docs/dashboard.md`, `docs/storage.md`, `data/providers/alpaca_news.py`, `data/providers/openbb.py`, `data/refresh.py`, `storage/office_db.py` (tabella `news`), `storage/retention.py` (`compact_news`), `tools/environment.py` (`news_by_ticker`, `news_by_theme`), `tools/schemas.py`, `runtime/jobs.py`, `runtime/scheduler.py`, `prompts/sentiment_analyst.md`, `config/office.toml`.

**Passo 0:** censisci cosa esiste (provider, tabella `news`, retention, cache in `data/refresh.py`, tool) e riparti da lì invece di duplicare. Riporta cosa hai trovato.

## Cosa costruire

1. **Fonti** (tabella `news_sources`, configurabili via comandi, default in `config/office.toml`):
   - `alpaca`: come oggi, con paginazione oltre le prime 50.
   - `rss`: feed aggiunti da Luca (URL, nome). Parser robusto (RSS 2.0 e Atom), timeout, limite di dimensione, niente esecuzione di contenuti, solo `http(s)`. Usa una libreria già presente o `feedparser` come dipendenza opzionale motivata.
   - `openbb`: notizie per società e mondo (`obb.news.company`, `obb.news.world`) tramite l'extra `openbb` già in `pyproject.toml`; se l'extra non è installato o la chiave manca, la fonte risulta `unavailable` con il motivo, senza rompere le altre.
   - **Calendario**: macro (`obb.economy.calendar` o alternativa motivata) ed earnings (`obb.equity.calendar.earnings`, oppure Alpaca/Yahoo se più affidabili), in una tabella `calendar_events`.
2. **Ingestione** come job del Runtime (scheduler esistente): ogni fonte con cadenza configurabile (default 15 min in seduta, 60 fuori), deduplica per URL normalizzato o hash di titolo+fonte, ticker associati in modo **deterministico** (simboli dati dal provider, cashtag, nomi delle società di portafoglio e watchlist), temi dal provider quando esistono. Nessuna chiamata LLM. Errori per fonte registrati (`last_error`) senza fermare le altre. Retention esistente (`compact_news`) invariata.
3. **Tool degli agenti**: `news_by_ticker` e `news_by_theme` leggono dall'archivio (tutte le fonti, con `id` di ciascuna notizia nel risultato); nuovi `news_search {q, ticker, since, limit}`, `economic_calendar {from, to}`, `earnings_calendar {from, to, tickers}`. Ruoli che li ricevono: come oggi più il calendario a PM, Market e Fundamental (motiva le scelte). Aggiorna i prompt interessati con una riga ciascuno.
4. **Traccia d'uso** (tabella `news_usage`): `read` quando una notizia compare nel risultato di un tool di un agente (con `cycle_id`, `chat_id`, `tool_call_id`), `cited` quando un agente la cita per `id` in un messaggio o in un fatto della scheda del ticker (aggiungi il campo `news_ids` facoltativo dove ha senso), `forwarded` per gli inoltri di Luca.
5. **Comandi per Luca** (`Idempotency-Key`, `X-Actor`, envelope `{ok, data, reasons}`):
   - `forward_news {news_id, to: {agent: str} | {ticker: str}, note: str}`: scrive nella chat del destinatario (per `ticker`, l'agente `ticker:<SYM>` nel topic del ticker; se l'agente del ticker non esiste ancora, il PM nel topic del ticker) un messaggio di Luca con titolo, fonte, link e nota; per il PM segue la regola attuale di `Say` (Scheduled task). Registra `forwarded`.
   - `add_news_source {provider: "rss", name, url}`, `set_news_source_enabled {source_id, enabled}`, `remove_news_source {source_id}`, `refresh_news {source_id: int|null}`.
6. **Eventi SSE** (al commit): `news.ingested {source_id, count}`, `news.used {news_id, agent, kind}`, `news.source {source}`.

## Contratto (vincolante: il frontend usa esattamente questi nomi)

Se lo cambi, aggiorna questo file e `docs/dashboard.md` nello stesso commit e scrivilo nel report. Timestamp ISO UTC.

```
NewsItem = {id, headline, summary|null, url|null, source, provider: "alpaca"|"rss"|"openbb",
            published_ts, fetched_ts, tickers: [str], themes: [str], image_url|null, has_full_text,
            in_portfolio, in_watchlist, usage: {reads, citations, forwards}}
```

- `GET /v1/read/news?ticker=&theme=&source_id=&provider=&scope=all|portfolio|watchlist&q=&before=&limit=` → `{items: [NewsItem], next_before: str|null}` dal più recente (default `limit` 50; `before` = `published_ts` o cursore opaco).
- `GET /v1/read/news_item?id=` → `NewsItem & {full_text|null, usage_detail: [{agent, kind: "read"|"cited"|"forwarded", ts, cycle_id|null, chat_id|null, topic|null, note|null}]}`.
- `GET /v1/read/news_sources` → `[{id, provider, name, url|null, enabled, status: "ok"|"error"|"unavailable", last_fetch_ts|null, last_error|null, items_24h}]`.
- `GET /v1/read/calendar?from=&to=&kind=macro|earnings` → `[{id, kind: "macro"|"earnings", ts, title, country|null, ticker|null, importance: "low"|"medium"|"high"|null, actual|null, forecast|null, previous|null, source, in_portfolio, in_watchlist}]` ordinati per `ts`.

## Scenario di sviluppo

Estendi `scripts/dev_cockpit_scenario.py` / `dev_cockpit_server.py`: 60–100 notizie da tutti e tre i provider su ticker di portafoglio, watchlist e altri; 4–5 fonti (una RSS in errore, OpenBB `unavailable` se l'extra manca); traccia d'uso con letture, citazioni e un inoltro; calendario con una settimana di eventi macro ed earnings. Nessuna rete nello scenario. Mai usato in produzione.

## Verifica

Test-first (skill `tdd`), provider simulati: ingestione e deduplica fra fonti; paginazione Alpaca; RSS malformato, timeout e schema non `http(s)` rifiutati; OpenBB assente → `unavailable` senza rompere le altre; associazione dei ticker; tool degli agenti dall'archivio con `id`; `news_usage` per `read`, `cited`, `forwarded`; `forward_news` verso agente, verso ticker con e senza agente del ticker, verso PM (Scheduled task); comandi sulle fonti; eventi solo al commit; idempotenza. Poi una lettura reale in sola lettura di un feed RSS pubblico e di Alpaca news se le chiavi ci sono, e smoke HTTP/SSE sul server di sviluppo (porta **8776**, `--db data/dev-cockpit-notizie-be.db`).

## Documentazione

`docs/dashboard.md` (endpoint, comandi, eventi), `docs/architecture.md` (sezione notizie aggiornata), `docs/storage.md` (tabelle nuove). Annota in `.scratch/notizie/wiki-notes-backend.md` cosa registrare nella wiki (la scrive la sessione principale).

## Fuori scope

`frontend/`, sintesi o punteggi LLM, social, scraping del testo integrale, notifiche.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere i sorgenti; Serena per il codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non committare `data/*.db*`, `nohup.out`, `.serena/`, `graphify-out/` (salvo il grafo se già tracciato), `frontend/tsconfig.tsbuildinfo`, chiavi o `.env`.
- Comandi: `.venv/bin/python -m pytest -q -p no:cacheprovider`, `.venv/bin/ruff check .`.
