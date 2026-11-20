# Handoff: shell + Terminale del cockpit (Impeccable, code-led)

Repo `/home/luca/trading-agent`, branch di partenza `docs/agent-restart`. Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: commit e push di codice e wiki (`/home/luca/trading-agent-wiki`).

## Da leggere prima

`PRODUCT.md`, `docs/frontend.md` (regole vincolanti), `.scratch/cockpit/brief-shell-terminale.md` (brief confermato da Luca), `.scratch/cockpit/chart-library.md` (libreria grafici), `docs/dashboard.md` (API del Runtime).

## Ambiente: leggere bene

Claude gira su un PC Linux headless (`192.168.68.107`, utente `luca`); Luca usa l'app Claude su un MacBook. **Luca vuole l'esperienza Impeccable completa.** Ogni pagina da aprire (pagine di scelta di Impeccable, dev server di Vite) va avviata qui (per Impeccable `IMPECCABLE_QUESTION_FORCE=1`) e a Luca va dato il comando da lanciare sul Mac, per esempio:

```bash
ssh -N -L 5173:127.0.0.1:5173 luca@192.168.68.107
```

poi `open http://127.0.0.1:5173/`. Mai ripiegare sulle domande in chat quando esiste una pagina.

## Decisioni già prese (non rimetterle in discussione)

- Mode **Operate**, build **code-led**, direzione **standard di categoria eseguito al meglio**, senza metafore: Luca ha scartato due giri di direzioni con metafore. Riferimenti di qualità: TradingView e IBKR TWS (Terminale); app di Claude, Linear e Slack (pannello Bridge e agenti). Componenti moderni e belli da app professionale, tema scuro unico, numeri tabulari.
- Il "collega jolly" pervade la UI: Luca legge e scrive gli stessi ambienti degli agenti via Runtime; ogni segno mostra il suo autore.
- Stack: React, TypeScript, Vite, Tailwind, shadcn/ui; 21st.dev per scoprire componenti. Sostituisci la bozza esistente in `frontend/` (è un anti-riferimento).
- Grafico: `lightweight-charts` v5.3 + `deepentropy/lightweight-charts-drawing`, adattatore `ChartState`; indicatori dal Runtime. Skill `lightweight-charts` e `dataviz`.

## Flusso Impeccable

1. `.claude/skills/impeccable/scripts/impeccable context`, poi `reference/new-work.md`. Il mondo è "canon" (standard di categoria): annotalo come impegno di brand in PRODUCT.md (già presente) e scrivi il direction contract nel surface brief (`impeccable surface-brief write`), con `seed: none (pinned)` e le parole di Luca che lo fissano.
2. Leggi `reference/craft-floor.md` prima di ogni modifica UI.
3. Costruisci: proxy Vite verso il Runtime, client tipizzato di `/v1` (comandi con `Idempotency-Key` e `X-Actor: cockpit`, letture, SSE con replay `Last-Event-ID`), shell, poi Terminale. Tutti gli stati del brief.
4. Verifica: `impeccable first-viewport ... --capture .impeccable/review` (desktop e mobile 390 px), `impeccable detect --json`, screenshot Playwright, poi `impeccable-finish-reviewer` e `impeccable-documenter` per `DESIGN.md`. Poi `/impeccable critique` e `/impeccable audit`.

## Dipendenze dal backend

Un'altra sessione aggiunge al Runtime barre OHLCV, indicatori, annotazioni condivise, `added_by` della watchlist e un dev server con dati finti (`.scratch/cockpit/handoff-backend-terminale.md`). Finché quel lavoro non è sul tuo branch: costruisci shell, watchlist, ordini e stati con gli endpoint che esistono già (`docs/dashboard.md`), e il grafico dietro l'adattatore `ChartState`. Non inventare dati in produzione; per sviluppo usa il Runtime di test (`build_test_office` + `Runtime`, vedi `tests/runtime/test_http.py`). Quando il branch del backend è pronto, chiedi a Luca se unirlo.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere sorgenti; `graphify update .` dopo modifiche al codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo modello `my-combo`, mai `free`. Lavoro pesante a subagenti.
- Non toccare il backend (`runtime/`, `storage/`, ecc.): lo fa l'altra sessione.
