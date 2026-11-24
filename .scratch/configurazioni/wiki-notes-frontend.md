# Configurazioni — note per il wiki (frontend)

Branch: `claude/configurazioni-frontend-ui-4e88cd`. Pagina `/configurazioni` (e `/configurazioni/:section[/:agent]`), sezioni `agenti`, `chiavi`, `mercato`, `dati`, `salute`.

## Da registrare nel wiki

- **Struttura**: indice delle sezioni con una riga di stato ciascuna + gruppo «Altrove» (Limiti di rischio → `/portafoglio?tab=risk`, Notizie, Terminale, Ufficio). Su telefono l'indice è la pagina e ogni sezione è una pagina a sé.
- **Impostazioni in bozza**: si modificano in riga, la barra in basso dice «N modifiche · Rivedi»; il pannello di revisione chiama `update_settings` con `dry_run: true`, mostra accettate/rifiutate e avvisi alla lettera, chiede il motivo e, per le voci `capital`, la conferma (`confirm: true`). Storico per sezione con Ripristina (`restore_settings`).
- **Prompt**: editor nella sezione Agenti, diff affiancato/unificato, versione N+1 con motivo, versioni con Ripristina (`restore_prompt`). Vale dal ciclo successivo.
- **Chiavi in sola scrittura**: campo password non controllato, mai precompilato, svuotato prima che la richiesta risponda; `set_secret` non passa da una mutation di react-query (la MutationCache terrebbe le variabili); il risultato è ricostruito campo per campo. Verificato con Playwright: il valore non compare in DOM, valori degli input, storage, URL, history, console; esce solo nel body di `POST /v1/commands/set_secret`. Le chiavi del broker richiedono la conferma esplicita; quelle da ambiente non si rimuovono dal cockpit.
- **Deep link Portafoglio**: `?tab=` (`risk`, …) apre la scheda indicata; ha la precedenza sulla scheda ricordata.
- **SSE** (`lib/runtime/provider.tsx` `keysFor`): `settings.updated` → cfg settings/agents/health; `prompt.updated` → cfg prompt/agents; `secret.updated` → cfg secrets/health; `health.changed` → cfg health/backups. Chiavi query `["cfg", kind, accountId, …]`.
- **Fixture di sviluppo**: `COCKPIT_SETTINGS_FIXTURES=1` (ufficio pieno) o `=empty` (installazione nuova) → middleware Vite in `frontend/dev/settings-fixtures.ts`, solo `vite serve`; l'intestazione mostra «Dati di esempio». Nel build non entrano (verificato su `dist/`).
- **DESIGN.md**: aggiunti Settings ledger, Draft bar and review sheet, Prompt editor, Write-only keys, Runtime health.

## Adapter in attesa del backend (nomi esatti del contratto)

Letture (`features/settings/api.ts`): `/v1/read/settings`, `settings_history`, `agent_configs`, `prompt?agent=`, `prompt_history?agent=`, `secrets`, `runtime_health`, `backups`. Finché rispondono 404 «Read endpoint not found», la sezione mostra «Non disponibile» con l'endpoint atteso.

Comandi: `update_settings`, `restore_settings`, `update_prompt`, `restore_prompt`, `set_secret`, `clear_secret`, `test_connection`, `backup_db`. Un 404 «Command … not found» diventa un messaggio che nomina il comando.

## Punti aperti per il backend

- **Diff di `update_prompt` in dry run**: il frontend usa `data.diff` solo se è una lista `[{op: "eq"|"add"|"del", text}]`; altrimenti calcola il diff da sé (LCS per righe). Proposta: adottare questa forma.
- **Testo di una versione vecchia del prompt**: il contratto non ha una lettura per il testo di una versione passata, quindi «Ripristina» mostra autore, motivo e data ma non l'anteprima del testo. Serve `GET /v1/read/prompt?agent=&version=` (o `text` in `prompt_history`).
- **Ripristino del database**: resta manuale (Runtime fermo, copia del backup); la UI lo dice e non offre un comando.
