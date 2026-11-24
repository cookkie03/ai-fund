# Wiki Notes (Backend): Configurazioni

Da registrare nella wiki (`system/interface/frontend-module.md`, `system/foundation/decision-log.md`, pagine di configurazione):
- `SettingsStore`: versionamento delle impostazioni di ufficio con `office.toml` come default v0, distinzione tra modifiche `live` e `restart`, validazione contro `BOUNDS`.
- `PromptStore`: versionamento dei prompt degli agenti con caricamento al ciclo successivo e calcolo diff.
- `SecretsManager`: chiavi API in file esterno con permessi `0600`, mai esposte in risposte/eventi/log, test di connessione in sola lettura.
- Salute del Runtime e backup online con rotazione.
