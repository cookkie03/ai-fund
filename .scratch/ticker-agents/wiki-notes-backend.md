# Note Backend per la Wiki (Agenti del Ticker e Scheda del Ticker)

Data: 2026-11-22
Branch: `ticker-agents-backend`
Documentazione interna per l'aggiornamento della wiki di progetto da parte della sessione principale.

## 1. Concetti di dominio aggiunti
- **Agente del ticker (`ticker_agent`)**: ruolo con identità persistente `ticker:<SYM>`, supervisore `portfolio_manager`. Coordina gli specialisti nella chat del ticker, formula la tesi e sottopone la proposta operativa (`submit_proposal`). Non ha permessi di creazione ordini.
- **Scheda del ticker (Dossier)**: stato strutturato persistito su tabella `dossier_versions` in formato append-only per versione (`ticker`, `version`, `ts`, `author`, `sections_json`, `document_json`).
  - Ogni fatto ha `author`, `ts`, `reference_date`, `confidence` e `status` (`active` | `stale` | `superseded`).
  - Marcatura automatica `stale` applicata in lettura sulle sezioni specialist (`dossier_stale_days`, default 30 giorni).
  - Storico accessibile tramite `/v1/read/dossier_history` e singole versioni immutabili tramite `/v1/read/dossier?ticker=&version=`.
- **Proposte (`proposals`)**: tabella persistente delle proposte inviate al PM (`ticker`, `agent`, `status`, `direction`, `conviction`, `sizing_fraction`, `risk_reward`, `submitted_ts`, `decided_ts`, `decided_by`, `reason`, `cycle_id`).
  - Stati proposta: `pending`, `accepted`, `deferred`, `rejected`, `asked`, `processing`.
  - Solo `accept` (da PM o da comando utente confermato) instanciano il calcolo della Bozza deterministica e il passaggio dal Risk Gate.

## 2. Punti di coordinamento con `portafoglio-backend`
- La migrazione per le tabelle `dossier_versions` e `proposals` è stata registrata come **migrazione 8** (`008_ticker_dossier_versions`), salvaguardando la **migrazione 7** (`007_portfolio_backend`) di `portafoglio-backend`.
- In `runtime/queries.py` e `storage/office_db.py`, le modifiche a `portfolio()` leggono le posizioni dallo snapshot più recente in modo non invasivo.
- Quando si effettua il merge tra `portafoglio-backend` e `ticker-agents-backend`, verificare la sequenza ordinata di migrazione 7 e 8.

## 3. Pagine wiki da aggiornare
- `system/orchestration/parallelism-design.md`: registrare l'adozione definitiva dell'Agente Single Ticker e della Scheda DB versionata.
- `system/investment/state-schemas.md`: allineare i campi del dossier con il contratto JSON vincolante.
- `system/agents/agents.md`: aggiungere il ruolo dell'agente del ticker (`ticker:<SYM>`) con configurazione condivisa `[agents.ticker_agent]`.
- `system/foundation/decision-log.md`: aggiungere la voce decisionale corrispondente all'ADR 0004.
