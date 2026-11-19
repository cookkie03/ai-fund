# Handoff — implementazione del Runtime unico (chat `/goal`)

## Goal (da incollare in `/goal`)

> Implementa il Runtime unico del trading-agent seguendo `.scratch/core-runtime/spec.md`, fette S1–S8 in ordine, test-first. Ogni fetta lascia la suite verde e ha un commit proprio. Hai finito quando la «Definizione di fatto» (§13 della spec) è verificata, la documentazione e la wiki sono aggiornate, codice e wiki sono pushati, e `.scratch/core-runtime/report.md` è scritto.

## Contesto in tre righe

Oggi ogni comando CLI costruisce un Office completo e scrive nel DB, e il motore controlla il DB ogni 0,5 s e Alpaca ogni 30 s. Luca ha deciso (2026-11-20) un **Runtime**: processo unico, unico writer del DB, comandi, letture ed eventi via HTTP + SSE, client sottili, nessun polling. La progettazione è chiusa: **non riaprire le decisioni**, implementale.

## Dove

- Repo codice: `trading-agent`, branch **`docs/agent-restart`** (non `main`, che è vecchio). Base: commit con ADR 0003 e spec, successivo a `6d228b3`. Path: `/Users/luca/Documents/Projects/trading-agent` sul Mac, `/home/luca/trading-agent` sul Minisforum. Prima di iniziare esegui `git pull`.
- Wiki: `trading-agent-wiki`, branch `main`. Sul Mac la copia locale `/Users/luca/Documents/Projects/trading-agent-wiki` ha modifiche vecchie non committate ed è indietro rispetto a `origin`: **non toccarla**. Lavora su un worktree pulito di `origin/main` (`git worktree add <dir> origin/main -b <branch>`, push con `git push origin HEAD:main`) oppure sulla copia del Minisforum.

## Leggi prima di scrivere codice (in quest'ordine)

1. `AGENTS.md` del repo: regole di wiki, skill e documentazione.
2. `.scratch/core-runtime/spec.md`: **la fonte vincolante**, inclusi interfacce, catalogo eventi, fette e criteri di accettazione.
3. `docs/adr/0003-runtime-unico-writer-event-driven.md` e `GLOSSARY.md` (sezione Runtime): usa questi termini nel codice e nei messaggi.
4. Wiki: `wiki/_meta/hot-cache.md`, `wiki/system/foundation/architecture.md#Runtime unico — 2026-11-20`, `wiki/system/interface/frontend-module.md`.
5. Codice da toccare: `workflows/office.py` (`run`, `run_once`), `storage/office_db.py` (`transaction`, migrazioni), `execution/order_flow.py` (`sync_broker_orders`, `approve`, `SystemHalt`), `execution/trade_manager.py`, `interface/cli.py`, `bootstrap.py`, `tests/interface/test_cli.py`, `compose.engine.yaml`.

## Come lavorare

- **Skill**: leggi e applica `tdd` per ogni fetta, `codebase-design` per le interfacce di `runtime/`, `code-review` su tutto il branch prima di chiudere.
- **Ordine delle fette**: S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8. S3 e S4 dipendono solo da S1; S7 da S1 e S3.
- **Commit**: uno per fetta, messaggio `feat(runtime): S<n> <titolo>`. Prima di ogni commit: `uv run pytest` e `uv run ruff check .` verdi.
- **graphify**: prima di leggere i sorgenti esegui `graphify query "<domanda>"`; dopo le modifiche al codice esegui `graphify update .`.
- **Dipendenze nuove**: `fastapi`, `uvicorn`, `httpx`, aggiunte con `uv add` e bloccate in `uv.lock`.
- **Test**: niente sleep reali. Clock e waiter vanno iniettati, broker e stream sono fake (`tests/fakes/`). Il test reale Alpaca resta sotto il marker `integration` e non è obbligatorio.
- **Deleghe** a `claude -p`: solo il modello `my-combo`, mai `free`.
- **Ignora** `openbb-ui/` e `telegram-claude/`: Telegram è fuori perimetro e il suo contratto futuro è `RuntimeClient`.
- **Non committare**: `data/trading-agent.db*`, `nohup.out`, `.serena/`, `graphify-out/`, `frontend/tsconfig.tsbuildinfo`.

## Quando fermarti e chiedere a Luca

Solo se ti serve una decisione **non** coperta dalla spec e il lavoro non può proseguire con un default reversibile. Esempi: cambiare una regola del Risk Gate, una semantica di ordine non descritta, un comportamento con capitale reale. Per tutto il resto scegli la soluzione più semplice coerente con la spec e annotala nel report come «scelta presa».

## Fine lavoro

1. Esegui `code-review` sul diff del branch dalla base della spec, poi correggi i problemi trovati.
2. Verifica la §13 della spec, incluso lo smoke con `curl -N …/v1/events`, e riporta l'output.
3. Aggiorna la documentazione: `docs/architecture.md`, `docs/office-engine.md`, `docs/dashboard.md` (riscritto come API del Runtime), `README.md`. Aggiorna la wiki: log in fondo, board, hot-cache, `system/foundation/implementation-status.md`. Distingui cosa è implementato da cosa è verificato.
4. Scrivi `.scratch/core-runtime/report.md` con:
   - fette fatte, con hash dei commit;
   - test eseguiti e risultati;
   - scelte prese senza Luca;
   - deviazioni dalla spec, con il motivo;
   - cosa resta e i rischi noti.
5. Esegui commit e push di codice (`docs/agent-restart`) e wiki (`main`).
6. Comunica a Luca che hai finito, con il link al report: lui lo porterà nella chat di progettazione per la review.

## Punto in sospeso, da non fare senza ok

`docs/frontend.md:21` dice ancora «Clearly distinguish paper and live trading». PRODUCT.md dice di non mostrare la modalità paper/live nella UI. La correzione aspetta l'ok di Luca e non fa parte di questo goal.
