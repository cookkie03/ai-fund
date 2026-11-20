# Handoff: backend del Runtime per il Terminale del cockpit

Repo `/home/luca/trading-agent`, branch di partenza `docs/agent-restart`. Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: test verdi, ruff pulito, `graphify update .`, commit e push (codice e, se tocchi decisioni, wiki `/home/luca/trading-agent-wiki`).

## Perché

Il cockpit ha sei pagine (`PRODUCT.md`, `docs/frontend.md`). La prima da costruire è il Terminale (`.scratch/cockpit/brief-shell-terminale.md`). Il frontend legge e scrive gli stessi ambienti degli agenti passando dal Runtime (idea del "collega jolly"). Per il Terminale mancano letture e scritture che oggi il Runtime non espone. API attuale: `docs/dashboard.md`. Architettura: `docs/adr/0003-runtime-unico-writer-event-driven.md`, `.scratch/core-runtime/spec.md`.

## Cosa fare (test-first, skill `tdd`)

1. **Barre OHLCV**: `GET /v1/read/bars?ticker=&timeframe=&start=&end=&limit=`. Stessa sorgente e stessa cache dei tool degli agenti (`OHLCVInput`, `data/cache.py`); timeframe di default `bar_timeframe` (1h). Formato adatto a lightweight-charts: `{time (UTC epoch s), open, high, low, close, volume}`.
2. **Indicatori**: `GET /v1/read/indicators?ticker=&timeframe=&names=ema20,rsi14,atr14&...`. Stessa definizione dei tool degli agenti (`IndicatorsInput`), serie allineate alle barre. Gli indicatori si calcolano qui, non nel browser (decisione in `.scratch/cockpit/chart-library.md`).
3. **Annotazioni del grafico** (ambiente condiviso agenti/Luca):
   - tabella `chart_annotations`: id, ticker, timeframe facoltativo, `drawing_json` (formato `Drawing` di `deepentropy/lightweight-charts-drawing`, punti `{time, price}`), `author` (`user` o nome agente), creato/aggiornato, stato `active`/`struck`. Niente cancellazioni fisiche: un'annotazione rimossa resta barrata con chi e quando;
   - comandi `upsert_annotation` e `strike_annotation` (idempotenti, `X-Actor`), lettura `GET /v1/read/annotations?ticker=&include_struck=`;
   - eventi SSE `annotation.created|updated|struck` nella tabella `events`.
   - I tool degli agenti sulle annotazioni NON fanno parte di questo lavoro (prossime versioni): progetta però lo schema perché possano usarlo senza migrazioni.
4. **Watchlist con autore**: aggiungi `added_by` (`user` o agente) alla watchlist e al DTO; i comandi `add_watchlist`/`remove_watchlist` lo valorizzano da `X-Actor` o dall'agente.
5. **Storico equity**: `GET /v1/read/equity_history?from=&to=` dagli snapshot di portafoglio (servirà al Portafoglio; facoltativo se costa molto).
6. **Dev server con dati finti per il frontend**: uno script/entrypoint documentato che avvia `build_test_office` + `Runtime` su una porta locale con barre e annotazioni di esempio, per lo sviluppo del cockpit senza broker né LLM (mai usato in produzione).
7. Aggiorna `docs/dashboard.md` (endpoint, eventi) e la wiki se cambia una decisione.

## Fuori scope

Bridge agent, stream delle chiamate ai tool, tool degli agenti sul grafico, CORS (il frontend usa il proxy di Vite).

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere i sorgenti.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo modello `my-combo`, mai `free`.
- Non committare `data/trading-agent.db*`, `nohup.out`, `.serena/`, `graphify-out/` (salvo il grafo se già tracciato), `frontend/tsconfig.tsbuildinfo`.
- Lavora in un worktree: il frontend viene costruito in parallelo in `frontend/` da un'altra sessione; non toccare `frontend/`.
