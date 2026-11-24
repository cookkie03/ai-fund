# HANDOFF: Deployable, Funzionante e Ordinato (Branch `public`)

> **Workspace:** `/home/luca/ai-fund/public`  
> **Branch Git:** `public` (basata su `origin/main`)  
> **Contesto Issue:** #10 (Docker Compose), #11 (Dev Launcher 1 comando), #15 (Configurazione sicura & `.env.example`), #32 (README)  
> **Data:** 2026-11-24  

---

## 1. Obiettivo della Sessione

Rendere il repository di `trading-agent` immediatamente **deployabile, riproducibile e ordinato** per l'ambiente pubblico/open-source o produzione locale, preservando intatti i moduli opzionali (`openbb-ui/`, `telegram-claude/`, `.scratch/`) e senza rinominare o unificare repository in questa fase.

---

## 2. Stato Completato in Questo Step

I seguenti interventi architetturali e di configurazione sono già stati implementati e collaudati in locale:

### A. Riproducibilità Python & Test Suite (Fix `pyproject.toml`)
- **Problema**: `pytest` falliva di default con `ModuleNotFoundError: No module named 'tests'`.
- **Risolto**: Aggiunto `pythonpath = ["."]` sotto `[tool.pytest.ini_options]` in `pyproject.toml`.
- **Verifica**: `uv run pytest -m "not integration"` passa con successo (**465 test verdi**).

### B. Template di Configurazione (`.env.example`)
- Creato `.env.example` completo alla radice con documentazione di tutte le chiavi:
  - Broker Alpaca Paper (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_TRADING_URL`)
  - LLM Endpoint / OmniRoute (`OMNIROUTE_API_KEY`, `OFFICE_LLM_ENDPOINT`)
  - Provider Dati Mercato (`DATA_PRICES_PROVIDER=yahoo`)
  - Parametri Runtime & Cockpit (`TRADING_AGENT_DB`, `TRADING_AGENT_API_PORT`, `COCKPIT_PORT`)

### C. Deployment Produzione Full-Stack (Issue #10)
- **`frontend/nginx.conf`**: Configurazione Nginx per SPA routing e reverse proxy trasparente verso `engine:8765/v1/` con streaming SSE non-buffered (`proxy_buffering off`, timeout esteso).
- **`Dockerfile.frontend`**: Build multi-stage (Node 22 + Nginx alpine) super leggera per servire il Cockpit.
- **`compose.yaml`**: Orchestrazione multi-servizio:
  - `engine`: Runtime Python con healthcheck automatico `/v1/health` e volume dati persistente `trading-agent-data`.
  - `cockpit`: Frontend web servito su porta 3000 con proxy integrato alle API dell'engine (risolve i problemi di CORS alla radice).
  - Connessione automatica alla rete `omniroute_default` per i modelli LLM locali.

### D. Launcher di Sviluppo a Singolo Comando (Issue #11)
- **`scripts/dev.sh`**:
  - Verifica automatica dei prerequisiti (`uv`, `npm`) e generazione di `.env` se mancante.
  - Rilevamento preventivo dei conflitti di porta (8765 e 5174).
  - Avvio coordinato di backend Runtime e frontend Vite con log colorati e prefissati (`[engine]`, `[cockpit]`).
  - Gestione del trap `SIGINT` / `EXIT`: chiusura pulita di tutti i sottoprocessi senza orfani su `Ctrl+C`.

### E. Documentazione Operativa (`README.md`)
- Riorganizzato il flusso di avvio:
  - Sezione chiara per **Sviluppo Locale** (`./scripts/dev.sh`).
  - Sezione chiara per **Produzione con Docker Compose** (`docker compose up -d --build`).

---

## 3. Vincoli e Decisioni Convalidate

1. **Cartelle da NON eliminare**: `openbb-ui/`, `telegram-claude/`, `.scratch/` sono mantenute intatte.
2. **Nessun rename / unificazione Wiki immediata**: La Wiki rimane esterna per ora (Issue #28 rimandata).
3. **Sicurezza segreti**: Nessun file `.env` reale committato; solo `.env.example`.

---

## 4. Azioni per la Nuova Chat su `public`

Nella nuova sessione aperta su questa branch, l'agente può:

1. Verificare lo stato git dei file modificati:
   ```bash
   git status
   ```
2. Testare l'avvio in modalità dev o la build dei container:
   ```bash
   ./scripts/dev.sh
   # oppure test build docker
   docker compose build
   ```
3. Committare le modifiche su branch `public`:
   ```bash
   git add pyproject.toml .env.example Dockerfile.frontend frontend/nginx.conf compose.yaml scripts/dev.sh README.md HANDOFF.md
   git commit -m "feat(deploy): full-stack docker compose, dev launcher, and env template"
   ```
