# Trading Agent

## Wiki prima di ogni attività

Per ogni richiesta relativa a questo progetto, prima di proporre soluzioni, progettare, modificare codice, configurare servizi o eseguire operazioni, consulta la wiki locale in `../trading-agent-wiki/`.

1. Leggi `../trading-agent-wiki/CLAUDE.md`, `wiki/_meta/hot-cache.md` e `wiki/overview.md` nella wiki per recuperare regole e contesto.
2. Usa `wiki/_meta/index.md` e una ricerca mirata per trovare e leggere le pagine pertinenti alla richiesta. Per sviluppo e architettura consulta anche `wiki/artifacts/piano-operativo-trading-agent.md`, `wiki/system/foundation/codebase-architecture.md`, `wiki/system/foundation/decision-log.md` e `wiki/artifacts/project-board.md`.
3. Basa il lavoro sui requisiti pertinenti e sulle istruzioni correnti di Luca. Segnala le contraddizioni che incidono sulla richiesta; distingui decisioni consolidate, proposte e reference storiche.
4. Verifica nel repository il comportamento effettivo: la wiki descrive specifiche e decisioni, non dimostra che codice, test o deploy funzionino. Il codice preesistente è materiale da valutare rispetto al piano di ripartenza; conserva quanto presente finché il lavoro richiesto non ne definisce la destinazione.
5. Registra nella wiki decisioni e avanzamenti rilevanti, seguendo la sua taxonomy e le regole di board, log e hot-cache.
6. Aggiorna la wiki man mano che ogni decisione viene presa (anche durante interviste di design come `grill-with-docs`), non a fine sessione: pagina tematica, `decision-log`, board, log e hot-cache. Committa e pusha la wiki insieme al lavoro.

Il codice Python vive in questo repository; documentazione, decisioni e backlog condivisi vivono nella wiki adiacente. Se la wiki non è accessibile, rendi esplicita la lacuna prima di procedere con attività che dipendono dai suoi requisiti.

## Skill di Matt Pocock

Conserva le skill installate in `.agents/skills/` e i relativi collegamenti. Per il lavoro sul progetto usa le skill pertinenti di Matt Pocock quando disponibili: `codebase-design` per interfacce e moduli, `domain-modeling` per concetti e terminologia, `tdd` per implementazione e test, `code-review` per revisioni, `writing-for-agents` per istruzioni agli agenti. Leggi la skill prima di applicarla.

## Consultazione e documentazione durante lo sviluppo

Quando lavori con sub-agent, assegna a un consulente dedicato le domande sulla wiki: le sue risposte devono derivare esclusivamente dalla wiki locale e indicare pagine e passaggi pertinenti. Usa il suo contesto per il lavoro sul codice; mantieni distinta la ricerca esterna sulla documentazione dei provider. Nelle sessioni successive ricrea il consulente se quello precedente non è disponibile.

A ogni modifica rilevante aggiorna insieme al codice i documenti interessati: README per avvio/stato, `docs/architecture.md` per struttura e dipendenze, ricerca tecnica per vincoli dei servizi, wiki per requisiti/decisioni/board/log/hot-cache. Distingui proposte, implementazioni e verifiche eseguite. Usa un sub-agent dedicato alla documentazione quando disponibile; le istruzioni di manutenzione sono in `docs/documentation.md`.

## Allineamento con GitHub — ogni task

Vale per **qualsiasi** task, anche solo documentale, e per **entrambi** i repository: `trading-agent` e `trading-agent-wiki`.

1. All'inizio: `git fetch` e `git pull --rebase` sul branch corrente di ciascun repository.
2. Alla fine: committa le modifiche del task, rifai `git pull --rebase` e pusha. Non committare mai i file esclusi (DB locali, `.env`, `.serena/`, `graphify-out/`, `nohup.out`).
3. Il task è finito solo quando `git status -sb` mostra il branch senza `ahead` né `behind` in entrambi i repository.

Se trovi modifiche locali che non sono tue, non scartarle: salvale su un branch `backup/<macchina>-<data>`, pushalo e segnalalo a Luca.

## GitHub: issue → branch → PR → check → merge

1. **Issue.** Riusa la GitHub Issue del task o aprine una con risultato atteso e criteri di accettazione. GitHub Issues è il tracker operativo; la wiki conserva decisioni e contesto. Non duplicare le issue in Linear.
2. **Branch.** Parti da `origin/main` aggiornato. Per il cockpit: **una branch per pagina**, `<pagina>-frontend` (es. `settings-frontend`), che contiene backend e frontend della pagina; le sessioni di frontend e backend lavorano in worktree propri e convergono su quella branch. Per lavori fuori dalle pagine: `<tipo>/<numero>-<slug>` (es. `fix/42-cockpit`). Riprendi il branch già associato se esiste. Non lavorare direttamente su `main`.
3. **PR.** Esegui i controlli locali pertinenti (test, ruff, typecheck, build, verifica nel browser per le pagine), pusha il branch e apri la PR verso `main` con `Closes #<numero>`, riepilogo e verifiche. Indica l'impatto di release più alto fra le modifiche: `none`, `patch`, `minor` o `major`.
4. **Check.** Controlla GitHub Actions: test backend offline e build frontend devono essere verdi prima di segnalare la PR come pronta. Se falliscono, correggi o segnala il blocco.
5. **Merge.** Lo esegue manualmente Luca, o l'agente quando Luca lo chiede esplicitamente per quella PR. L'agente non abilita auto-merge.

## Versioni e release

Usa SemVer `vMAJOR.MINOR.PATCH` per il prodotto integrato. Classifica per effetto su chi usa il prodotto o integra i suoi contratti, non per dimensione del diff:

- **`none`** — documentazione interna, CI o refactor senza effetti osservabili per chi usa il prodotto.
- **`patch`** — bug fix, sicurezza o prestazioni compatibili; nessuna nuova capacità.
- **`minor`** — nuova capacità compatibile, per esempio una vista del cockpit o un endpoint aggiuntivo.
- **`major`** — rottura di un contratto supportato, per esempio API/config incompatibile, migrazione manuale obbligatoria o funzione rimossa. Prima di `v1.0.0`, le rotture deliberate possono uscire con un bump `0.x.0` (mai `0.x.y` come patch): chiamale `major` nella PR e documenta la migrazione. `v1.0.0` è una decisione esplicita di stabilizzazione.

Il bump della release segue l'impatto più alto dall'ultimo tag stabile; se tutte le modifiche sono `none`, salta la release. Luca sceglie il tag e avvia manualmente **Actions → Release** da `main`. Il workflow ricontrolla il commit e pubblica tag e note, senza deploy. Per comandi, worktree e procedura di rilascio, leggi `docs/git-workflow.md`.
