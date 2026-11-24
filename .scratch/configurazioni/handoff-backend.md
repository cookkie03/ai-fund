# Handoff: configurazione versionata, prompt, chiavi e salute del Runtime (backend)

Repo `/home/luca/trading-agent`, branch **`configurazioni-frontend`** (la branch della pagina, già creata da `main` e pushata). Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: test verdi, ruff pulito, `graphify update .`, commit e push su `configurazioni-frontend`. Non aprire la PR e non unire su `main`: lo fa la sessione principale dopo il frontend.

**Quando partire e dove:** i backend del Bridge (`assistente-frontend`) e delle Notizie (`notizie-frontend`) toccano gli stessi file del Runtime (`runtime/commands.py`, `runtime/queries.py`, `runtime/core.py`, `storage/office_db.py`, `config/office.toml`, scenario di sviluppo). **Parti quando almeno il Bridge è unito su `main`**, e porta prima `configurazioni-frontend` su `main` aggiornato (`git merge origin/main`). Lavora in un worktree tuo su `configurazioni-frontend` se il checkout principale è occupato. Non toccare `frontend/`: lo fa un'altra sessione in parallelo, con il contratto qui sotto.

## Obiettivo

Leggi `.scratch/configurazioni/brief.md` per primo. Rendere la configurazione dell'ufficio leggibile e modificabile dal cockpit attraverso il Runtime: impostazioni versionate con validazione e ripristino, prompt degli agenti versionati, chiavi API in sola scrittura, salute del Runtime.

## Da leggere

- Wiki (`/home/luca/trading-agent-wiki/wiki/`): `system/interface/frontend-module.md`, `system/foundation/decision-log.md`, pagine su configurazione, budget e retention (`grep -ril "office.toml\|retention\|budget" wiki/system`).
- Repo: `AGENTS.md`, `docs/adr/0003-runtime-unico-writer-event-driven.md`, `docs/dashboard.md`, `docs/storage.md`, `config/office.toml`, `config/office_settings.py`, `config/settings.py`, `prompts/loader.py`, `prompts/*.md`, `execution/risk_limits.py` (`RiskLimitsStore`, `BOUNDS`, `active_gate_limits`: **il modello da seguire**), `runtime/scheduler.py`, `runtime/jobs.py`, `runtime/http.py`, `runtime/queries.py` (`health`), `storage/retention.py`, `bootstrap.py`.

**Passo 0:** censisci come oggi si leggono `office.toml`, i prompt e le chiavi (chi li carica, quando, se a caldo) e riparti da `RiskLimitsStore` invece di inventare un secondo meccanismo. Riporta cosa hai trovato.

## Cosa costruire

1. **Impostazioni versionate** (`SettingsStore`, stessa forma di `RiskLimitsStore`): `office.toml` resta il default; le modifiche dal cockpit sono versioni nel DB che lo sovrascrivono. Per ogni chiave: tipo, limiti (`BOUNDS`), descrizione in italiano, sezione, `apply: "live"|"restart"`. Sezioni e chiavi: `agents.<id>.{model, endpoint, effort, daily_budget_usd}`, `schedule.*`, `market.bar_timeframe`, `max_parallel`, `scheduled_task_min_days`, `scheduled_task_max_days`, `budgets.*`, `approval_mode` (capitale: `confirm:true`), `retention.*`, `db_size_alert_mb`. **Esclusi** (vivono altrove): limiti di rischio (`update_risk_limits` esistente), fonti delle notizie (`notizie-frontend`). Le letture del motore passano dallo store, così le modifiche `live` valgono senza riavvio (motore, scheduler, budget); quelle `restart` sono salvate e segnalate come in attesa. Cambiare `bar_timeframe` va validato con la nota della wiki sui coefficienti `k` (avviso nella preview).
2. **Prompt versionati** (`PromptStore`): `prompts/*.md` resta il default; versioni nel DB con autore, motivo, data; `prompts/loader.py` legge la versione attiva al **ciclo successivo** (mai a metà ciclo). Diff calcolato lato server. Ripristino = nuova versione uguale a una vecchia.
3. **Chiavi API in sola scrittura.** Chiavi gestite: `OMNIROUTE_API_KEY`, `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` (coppia, come la validazione in `config/settings.py`), e quelle dei provider dati se esistono (OpenBB). Salvataggio **fuori dal repository e fuori dal DB**: file dedicato con permessi `0600` (es. `~/.config/trading-agent/secrets.env`, percorso configurabile), scrittura atomica; precedenza documentata rispetto a `.env` e alle variabili d'ambiente. Il valore non compare mai in risposte, eventi, log, `commands`/`events` (redigi il payload prima di salvarlo), eccezioni o tool degli agenti. Dopo il salvataggio, test di connessione in sola lettura (OmniRoute: elenco modelli; Alpaca: account) e ricarica dei client a caldo se possibile, altrimenti `restart`. Le chiavi del broker chiedono `confirm:true`. Il server HTTP resta su `127.0.0.1`.
4. **Salute del Runtime**: versione e commit, avvio e uptime, job dello scheduler con ultima esecuzione/esito/prossima, ultimi errori (dai log o dalla tabella eventi), dimensione del DB e del WAL, ultimo backup, connessioni SSE aperte, stato di broker e provider LLM.
5. **Backup del DB**: comando `backup_db` (backup SQLite online in `data/backups/`, rotazione configurabile); elenco dei backup in lettura. Il ripristino resta manuale e documentato (non dalla UI).
6. **Comandi** (`Idempotency-Key`, `X-Actor`, envelope `{ok, data, reasons}`), tutti con `dry_run` per la preview:
   - `update_settings {changes: {<key>: value}, reason, confirm: bool, dry_run: bool}` → preview `{changes: [{key, old, new, apply, ok, reason|null}], warnings: [str]}`; `confirm:true` obbligatorio se tocca `approval_mode`.
   - `restore_settings {version, reason}`.
   - `update_prompt {agent, text, reason, dry_run}` (preview con diff), `restore_prompt {agent, version, reason}`.
   - `set_secret {name, value, reason, confirm: bool}` → `data: {name, set: true, last4, test: {ok, detail}}`; `clear_secret {name, reason, confirm: true}`; `test_connection {target: "omniroute"|"alpaca"|"openbb"}`.
   - `backup_db {}`.
7. **Eventi SSE** (al commit): `settings.updated {version, keys}`, `prompt.updated {agent, version}`, `secret.updated {name, set}` (mai il valore), `health.changed`.

## Contratto (vincolante: il frontend usa esattamente questi nomi)

Se lo cambi, aggiorna questo file e `docs/dashboard.md` nello stesso commit e scrivilo nel report. Timestamp ISO UTC.

- `GET /v1/read/settings` → `{version, updated_ts, updated_by, pending_restart: [key], sections: [{id, title, items: [{key, label, description, type: "int"|"float"|"string"|"enum"|"time"|"bool", value, default, min|null, max|null, options: [str]|null, unit|null, apply: "live"|"restart", capital: bool, overridden: bool}]}]}`
- `GET /v1/read/settings_history?limit=` → `[{version, ts, actor, reason, changes: [{key, old, new}]}]`
- `GET /v1/read/agent_configs` → `[{agent, role, model, endpoint, effort, daily_budget_usd, today_cost, prompt_version, prompt_updated_ts}]` (agenti `core` e la configurazione unica `ticker_agent`).
- `GET /v1/read/prompt?agent=` → `{agent, version, text, updated_ts, updated_by, reason, is_default}`
- `GET /v1/read/prompt_history?agent=&limit=` → `[{version, ts, actor, reason, chars}]`
- `GET /v1/read/secrets` → `[{name, label, set: bool, last4|null, updated_ts|null, updated_by|null, source: "store"|"env"|"none", test: {ok, detail, ts}|null}]`
- `GET /v1/read/runtime_health` → `{version, commit, started_ts, uptime_s, db: {path_label, size_bytes, wal_bytes, alert_mb, last_backup_ts|null}, jobs: [{name, last_run_ts|null, last_status: "ok"|"error"|null, last_error|null, next_run_ts|null}], errors: [{ts, source, message}], sse_clients, broker: {ok, detail}, llm: {ok, detail}}`
- `GET /v1/read/backups` → `[{name, ts, size_bytes}]`

## Scenario di sviluppo

Estendi `scripts/dev_cockpit_scenario.py` / `dev_cockpit_server.py`: storico impostazioni con 3 versioni (una con chiave `restart` in attesa), prompt con 2–3 versioni per due agenti, segreti finti in un file temporaneo dello scenario (uno impostato, uno no, un test fallito), salute con un job in errore, due backup. Nessuna chiave reale, nessuna rete. Mai usato in produzione.

## Verifica

Test-first (skill `tdd`):
- validazione contro i limiti; `dry_run` non scrive; storico e ripristino; `approval_mode` senza `confirm` rifiutato; modifica `live` letta dal motore al ciclo successivo, `restart` marcata in attesa;
- prompt: versione nuova usata dal ciclo successivo e non da quello in corso; diff; ripristino;
- segreti: **il valore non compare** in risposta, eventi, tabella `commands`, log catturati, eccezioni, `GET /v1/read/secrets` (test esplicito che cerca la stringa ovunque); file con permessi `0600`; coppia Alpaca incompleta rifiutata; `clear_secret`; test di connessione simulato;
- `backup_db` produce un DB leggibile; rotazione;
- eventi solo al commit; idempotenza.
Poi smoke HTTP/SSE sul server di sviluppo (porta **8778**, `--db data/dev-cockpit-configurazioni-be.db`). Fai fare una revisione di sicurezza mirata al percorso dei segreti (skill `security-review` o subagente) e riportane l'esito.

## Documentazione

ADR `docs/adr/0006-configurazione-versionata.md` (impostazioni, prompt e segreti: dove vivono, precedenze, cosa vale a caldo), `docs/dashboard.md`, `docs/storage.md`, README se cambia l'avvio (percorso dei segreti). Annota in `.scratch/configurazioni/wiki-notes-backend.md` cosa registrare nella wiki (la scrive la sessione principale).

## Fuori scope

`frontend/`, limiti di rischio (già esistenti), fonti delle notizie, ripristino del DB dalla UI, utenti e permessi, aggiunta di agenti.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere i sorgenti; Serena per il codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo `~/.local/bin/claude-my-combo`, mai `free`, e **mai** con segreti, `.env` o il file dei segreti nel prompt. Subagenti solo Sonnet o Haiku.
- Non committare `data/*.db*`, `data/backups/`, `nohup.out`, `.serena/`, `graphify-out/` (salvo il grafo se già tracciato), `frontend/tsconfig.tsbuildinfo`, `.env`, file dei segreti.
- Comandi: `.venv/bin/python -m pytest -q -p no:cacheprovider`, `.venv/bin/ruff check .`.
