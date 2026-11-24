# Piano di unificazione

Branch: `unify/main` (da `main` = `db765d6`). Nessun push. Nessuna cartella o worktree cancellato.

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

- **Migrazioni DB rinumerate.** Tre rami usavano `009`. Ora: `009` Configurazioni, `010` Notizie, `011` Bridge. Un DB locale che ha già applicato una `009` di Notizie o Bridge darebbe errore su `010`/`011`: ricrearlo o allinearlo a mano.
- **Shell frontend.** Vince la `Sidebar` shadcn di `main`. Dall'Assistente restano: `/` accende la voce Assistente (`useHomeActive`) e il pannello Bridge è nascosto su `/assistente`.
- **Sheet.** `onOpenAutoFocus` (Radix) sostituito da `initialFocus={false}` (Base UI).
- **Pannello Bridge.** `bridge.tsx` prende la versione dell'Assistente, che sostituisce il segnaposto.

## Lavoro non committato salvato

Rami di sicurezza, creati senza toccare i worktree originali:
`wip/ai-fund-public` (Docker/deploy), `wip/terminale-ui-2026` (frontend alternativo), `wip/backend-terminale`, `wip/github-workflow`.
Da decidere: se tenerli, unirli o scartarli. Non sono in `unify/main`.

## Da fare (richiede il via di Luca)

1. Revisione e PR `unify/main` -> `main` (nessun push diretto su `main`).
2. Rendere `/home/luca/ai-fund` il repo principale. Oggi non è un repo git: contiene i worktree `public` e `shadcn-ui-migration`. Proposta: clone fresco dopo il merge su `main`, vecchia cartella rinominata `ai-fund.old`.
3. Pulizia di worktree e rami vecchi, solo dopo la validazione.
