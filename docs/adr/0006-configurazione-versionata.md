# ADR 0006: Configurazione Versionata, Prompt e Segreti

## Contesto
La pagina Configurazioni del cockpit richiede impostazioni di ufficio versionate, prompt degli agenti versionati, chiavi API gestite in sola scrittura fuori dal repository e dal DB con permessi strict (`0600`), e salute del Runtime.

## Decisione
1. **Impostazioni versionate** (`SettingsStore`): `office.toml` è il default (v0); le modifiche dal cockpit creano versioni in `settings_versions` con attore, motivo, prima e dopo. Le modifiche `live` vengono lette dal motore e scheduler; quelle `restart` sono salvate e segnalate come in attesa.
2. **Prompt versionati** (`PromptStore`): prompt in `prompts/*.md` come default; versioni salvate in `prompt_versions`. Il caricamento legge la versione attiva al ciclo successivo.
3. **Segreti in sola scrittura** (`SecretsManager`): file dedicato fuori da repo e DB con permessi `0600` (`~/.config/trading-agent/secrets.env`), scrittura atomica. Precedenza su `.env` e variabili d'ambiente. I valori non compaiono mai in log, risposte o eventi.
4. **Salute e Backup**: endpoint `runtime_health` completo, comando `backup_db` per backup online in SQLite e rotazione.
