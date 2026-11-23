# Git e GitHub

`AGENTS.md` definisce il flusso operativo e i criteri di versione. Questa pagina raccoglie i comandi e la procedura di rilascio.

## Workspace e controlli

- Usa il checkout corrente quando è libero; usa un worktree separato se Luca lo chiede o serve isolare un'altra attività. Non spostare o includere file locali estranei al task.
- A fine task codice e wiki devono risultare allineati con `origin`, senza `ahead` né `behind` (procedura in `AGENTS.md`).
- Usa Conventional Commits. Per verificare una PR su GitHub: `gh pr checks --watch`. I controlli CI sono `Backend tests (offline)` e `Frontend build`.
- Per allineare la wiki, aggiorna le pagine pertinenti a decisioni e procedure. Non pubblicare credenziali, database locali o transcript.

## Pubblicare una versione

1. Dopo il merge, controlla i tag e le PR dall'ultima release. Applica i criteri di `AGENTS.md` e scegli il prossimo tag stabile. Il tag Git è la versione del prodotto integrato; `pyproject.toml` e `frontend/package.json` restano metadati dei singoli componenti.
2. Vai in **Actions → Release → Run workflow**, seleziona `main` e inserisci il tag. Il workflow ripete la CI sul commit selezionato da GitHub, verifica che il tag sia crescente e crea la GitHub Release con note generate. Rileggi le note e aggiungi eventuali istruzioni di migrazione.
3. Verifica in **Releases** che tag, commit e note siano corretti. La procedura non pubblica pacchetti o immagini e non esegue deploy.

Come riferimento: [OmniRoute](https://github.com/cheaper-inference/OmniRoute) distingue l'accettazione di una release dalla pubblicazione dei pacchetti. Qui si riusa la CI e non si aggiungono job di distribuzione.
