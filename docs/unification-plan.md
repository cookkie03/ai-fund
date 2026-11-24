# Piano di unificazione

Branch: `unify/main` (da `main` = `db765d6`), pubblicato nella PR #34. Nessuna cartella o worktree cancellato.

## Ordine dei merge

| # | Ramo | Conflitti | Verifica |
|---|---|---|---|
| 0 | `integrate-pages`, `main-merge`, `cockpit-backend-terminale`, `ticker-agents-frontend` | nessuno: già in `main` | n/a |
| 1 | `shadcn-ui-migration` (PR #33) | 0 | pytest 465, typecheck, build |
| 2 | `configurazioni-frontend` (backend) | 0 | pytest 481 |
| 3 | `notizie-frontend` (backend) | 6, entrambi i lati | pytest 496 |
| 4 | `assistente-frontend` (backend) | 9, entrambi i lati, scenario dev a mano | pytest 515 |
| 5 | `claude/configurazioni-frontend-ui-4e88cd` | 1 (`vite.config.ts`) | typecheck, build |
| 6 | `claude/notizie-frontend-ui-a38556` | 4 | typecheck, build |
| 7 | `claude/assistente-frontend-ui-a54415` | 10, base shadcn + funzioni Assistente | typecheck, build |

Stato finale: `pytest` 515 passati, `npm run typecheck` e `npm run build` verdi.

## Scelte da conoscere

- **Migrazioni DB rinumerate.** `009` Configurazioni, `010` Notizie, `011` Bridge. La `012` crea le tabelle di Configurazioni se una vecchia migrazione `009` di un altro ramo aveva già occupato il numero. Verificato su quattro snapshot SQLite con `PRAGMA integrity_check`, senza migrare gli originali.
- **Shell frontend.** Vince la `Sidebar` shadcn di `main`. Dall'Assistente restano: `/` accende la voce Assistente (`useHomeActive`) e il pannello Bridge è nascosto su `/assistente`.
- **Sheet.** `onOpenAutoFocus` (Radix) sostituito da `initialFocus={false}` (Base UI).
- **Pannello Bridge.** `bridge.tsx` prende la versione dell'Assistente, che sostituisce il segnaposto.

## Lavoro non committato salvato

Rami di sicurezza, creati senza toccare i worktree originali:
`wip/ai-fund-public` (Docker/deploy), `wip/terminale-ui-2026` (frontend alternativo), `wip/backend-terminale`, `wip/github-workflow`.
`wip/ai-fund-public` è stato integrato; il prototipo `terminale-ui-2026` è conservato come riferimento, fuori dalla build. Gli altri rami di sicurezza restano separati.

## Passaggio al checkout principale

1. Dopo il merge della PR #34, verificare che la #33 sia interamente assorbita prima di chiuderla. Rinominare il repository GitHub in `ai-fund`.
2. Preparare un clone di `main` in un percorso adiacente, senza sovrascrivere `/home/luca/ai-fund`. Verificare il commit e ripetere test offline, typecheck e build.
3. Copiare `raw/` nel nuovo checkout con permessi privati, verificare contenuti e integrità contro l'originale e controllare con `git check-ignore raw/` e `git ls-files -- raw/` che la cartella sia ignorata e non tracciata. `.gitignore` non retroagisce sulla storia del vecchio repository wiki.
4. Inventariare e salvare modifiche, rami locali, dati e worktree. Per i worktree `public` e `shadcn-ui-migration`, mantenere i riferimenti Git validi durante lo spostamento (`git worktree move` o `git worktree repair`). Solo dopo la verifica promuovere il clone a `/home/luca/ai-fund`. Nessuna eliminazione degli originali senza conferma specifica.

## Progetto: wiki locale -> GitHub Wiki

Stato rilevato (`/home/luca/trading-agent-wiki`): vault Obsidian con `wiki/` (105 file `.md`, 1,6 MB) e `raw/` (363 file, 383 MB).
Il repo `cookkie03/trading-agent-wiki` e il repo codice sono **pubblici**.

### Regola di sicurezza (bloccante)
La GitHub Wiki di un repo pubblico è pubblica. Pubblicare solo pagine e allegati approvati da `wiki/`, dopo una revisione di contenuti e link. Non pubblicare mai `raw/`:
- contiene conversazioni personali, videochiamate, audio WhatsApp (`.opus`, `.m4a`) e note giornaliere;
- pesa 383 MB (le wiki GitHub non sono pensate per questo).

Nota: `raw/` oggi è già tracciato (298 file) nel repo pubblico `trading-agent-wiki`. Va valutato a parte se togliere quei file dalla storia pubblica. Non è parte di questa migrazione e non è stato toccato.
Escludere i file di stato del browser e ogni altro dato locale di autenticazione dalla migrazione.

### Struttura di destinazione
- `Home.md`: da `wiki/overview.md`.
- `_Sidebar.md`: una sezione per cartella (`system`, `strategy`, `prior-art`, `artifacts`, `syntheses`, `_meta`), con un link per pagina.
- Pagine: **nomi file piatti** (la Wiki GitHub non ha cartelle). Prefisso per evitare collisioni, es. `system-agents-agents.md`. Esistono già nomi duplicati (es. `architecture.md`), quindi il prefisso è obbligatorio.
- Link: `[[system/foundation/architecture]]` va riscritto come `[[system-foundation-architecture]]` (con script, mappa vecchio->nuovo percorso, report dei link rotti).
- Media: solo i pochi file in `wiki/` che servono; vanno in `images/` nel repo wiki o committati nel repo codice e linkati. Frontmatter Obsidian e canvas/base: non supportati, da togliere o convertire.

### Procedura
1. Script in `scripts/wiki_to_github.py` (sola lettura su `trading-agent-wiki/wiki`, scrive in una cartella di output vuota).
2. Dopo il rename, inizializzare la Wiki dalla UI se necessario. Il repository Wiki di destinazione sarà `https://github.com/cookkie03/ai-fund.wiki.git`.
3. Controllo a secco: elenco link rotti e collisioni, nessun push.
4. Push della Wiki solo dopo ok esplicito di Luca.
