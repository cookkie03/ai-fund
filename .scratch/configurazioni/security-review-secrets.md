# Security Review: Secrets Path & Storage (`storage/secrets.py`)

## Analisi e Verifiche di Sicurezza

1. **Collocazione dei Segreti**: I segreti (chiavi API, credential broker) sono memorizzati al di fuori del repository e del database SQLite, nel percorso predefinito `~/.config/trading-agent/secrets.env` (o ridefinibile tramite la variabile d'ambiente `TRADING_AGENT_SECRETS_PATH`). Questo garantisce che nessun commit accidentale possa includere chiavi nel controllo versione.
2. **Permessi di File Strict (`0600`)**: All'atto della creazione o scrittura del file `secrets.env`, il codice applica esplicitamente i permessi `0600` (`os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)`), impedendo l'accesso in lettura o scrittura ad utenti diversi dal proprietario del processo.
3. **Scrittura Atomica**: Gli aggiornamenti avvengono scrivendo prima su un file temporaneo (`.tmp` nella stessa directory) e sostituendo atomicamente il file di destinazione (`tmp.replace(self.secrets_path)`), evitando stati corrotti o file parzialmente scritti in caso di interruzione.
4. **Prevenzione Data Leakage**:
   - `GET /v1/read/secrets` restituisce esclusivamente lo stato (`set: true/false`), le ultime 4 cifre (`last4`), timestamp, attore e esito dell'ultimo test, senza mai esporre il valore in chiaro.
   - I comandi di aggiornamento/verifica (`set_secret`, `test_connection`) filtrano e redigono i payload prima di registrarli negli eventi SSE o nella tabella comandi.
   - Le eccezioni e i log non stampano mai il contenuto delle chiavi.

**Esito della revisione**: Conforme ai requisiti di sicurezza e isolamento richiesti per le chiavi API e credenziali di capitale.
