# Trading Agent

Progetto Python per un sistema multi-agente di analisi e gestione di un portafoglio azionario. Gli agenti elaborano informazioni e proposte; calcoli, controlli di rischio ed esecuzione restano deterministicamente verificabili.

## Avanzamento parziale al 2026-11-05

Il grafo prototipale `agents/graph.py` è separato dal runtime e usa analisti, PM e controlli iniettati; il routing è provvisorio. Quattro desk deterministici limitati, un Portfolio Manager con backend iniettato e astensione e un adapter di rischio per proposte long sono disponibili separatamente. Nessuna integrazione provider o broker né ragionamento agentico pieno. `agents/desk_adapters.py` collega i quattro desk richiedendo evidence e usando il timestamp della fonte più vecchia; il gate verifica identità del symbol e direzione long. L'adapter PM espone `pm_decision` mantenendo l'esito del grafo `pending`. Nessun backend reale; routing non deciso. Il clock è iniettabile: senza clock il grafo usa `now` fornito dal chiamante, adatto al replay ma non a rilevare il tempo trascorso durante il PM. Verificati `uv run pytest -q` (200 passati, 1 saltato, 2 warning) e `uv run ruff check agents/graph.py agents/desks.py agents/desk_adapters.py agents/portfolio_manager.py agents/portfolio_manager_adapter.py agents/risk_adapter.py tests/agents` (superato). Dettagli in [architettura](docs/architecture.md).

## Stato verificato al 2026-11-02

Nel workspace attuale, inclusi test locali non tracciati preesistenti, la suite riporta **157 passed, 1 skipped, 2 warning**. Il test Alpaca paper saltato richiede `--alpaca-paper`. Lint e build frontend sono passati.

La review PM è sperimentale: un reviewer iniettato può approvare l'esecuzione se supera i controlli strutturali e il risk gate. L'adapter OmniRoute locale usa `OMNIROUTE_API_KEY` e `OMNIROUTE_MODEL` (default `my-combo`). Verificati E2E offline simulato e percorso provider simulato → OmniRoute reale → dashboard con decisione pending e broker simulato. Non usare il percorso con un broker reale: la validazione delle citazioni non verifica la qualità della tesi.

## Configurazione

`config.Settings` centralizza i parametri runtime e legge `.env` quando il comando lo abilita. I segreti Alpaca devono essere forniti insieme; una configurazione parziale viene rifiutata. I default locali sono `data/trading-agent.db`, `localhost` e porta `8000`.

## Development locale

Per eseguire i comandi del motore in locale:

```bash
uv run trading-agent <cmd>
```

Le formule pure disponibili in `analysis/indicators.py` sono SMA, EMA, RSI Wilder, MACD, ATR Wilder e Pivot Points classici. Sono funzioni deterministiche testate.

## Ricerca tecnica

Il confronto datato con TradingAgents, Qlib, QuantLab e vectorbt è in [`docs/research/prior-art-benchmark.md`](docs/research/prior-art-benchmark.md). Le repository esterne sono riferimenti selettivi: non sostituiscono i contratti locali, la provenance SQLite o il replay canonico.

## Esecuzione con Docker

In produzione o sul server:

```bash
docker compose -f compose.engine.yaml up -d --build
```

Per interagire con la CLI del container in esecuzione:

```bash
docker compose -f compose.engine.yaml exec -T engine uv run --no-sync trading-agent <cmd>
```

## Ricerca semantica con MemPalace

MemPalace è una dipendenza runtime del progetto e usa il palace condiviso in
`/home/luca/.config/mempalace/palace`. Per verificare l'installazione e la ricerca:

```bash
uv run mempalace --version
uv run mempalace --palace /home/luca/.config/mempalace/palace status
uv run mempalace --palace /home/luca/.config/mempalace/palace search "query semantica"
claude mcp get mempalace
```

Il server MCP deve puntare a `mempalace-mcp --palace /home/luca/.config/mempalace/palace`.
La raccolta mantiene il repository principale e tutti i worktree Git registrati; prima di
rimuovere dati usare sempre `sync --dry-run` e verificare il report.

## Strategy state

