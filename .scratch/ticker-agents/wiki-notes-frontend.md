# Agenti del ticker e scheda del ticker: note frontend per la wiki

Branch: `claude/ticker-agents-frontend-df5ea6` (non mergiato). Backend atteso: `ticker-agents-backend` (non ancora esistente al momento del lavoro).

## Da registrare nella wiki

- **Ufficio a due livelli.** La pagina si legge da sinistra a destra come il grafo degli agenti: PM + coda "In attesa del PM" → Desk dei ticker (un agente `ticker:<SYM>` per riga, "riporta a PM") → specialist "chiamati dagli agenti del ticker". Hover su una riga ticker illumina gli specialist che ci lavorano, e viceversa. Filtri: Tutti, In analisi, In attesa del PM, In portafoglio, Inattivi; ricerca sopra 10 righe; densità fino a 40 ticker con container query.
- **Agenti del ticker come autori.** `author("ticker:NVDA")` → "Agente NVDA", monogramma = ticker, colore unico porcellana `--author-ticker` (il colore resta identità della squadra core).
- **Coda proposte e decisione di Luca.** Righe in ordine di attesa; "Decidi" apre "Decidi al posto del PM" (Accetta/Rimanda/Rifiuta/Chiedi, motivazione obbligatoria, ridimensiona per Accetta, data per Rimanda). Invia `decide_proposal` con `confirm:true`. Halt disabilita Accetta. Il Risk Gate resta sovrano.
- **Vista agente.** Per gli agenti del ticker: link forte "Scheda SYM" e striscia della scheda (versione, stato, direzione, conviction, fatti vecchi). Per il PM: coda proposte sopra lo stream dei tool; su telefono tab "Proposte". Chat multiple, tool espandibili, scrivi, assegna task, costi/token invariati.
- **Scheda del ticker `/ticker/:symbol`.** Mosaico: header (prezzo, settore, stato scheda e versione, agente del ticker e stato, posizione se investita, link a Grafico/Chat/Portafoglio, legenda Firme), Tesi + Proposta e Risk Gate (scala stop–ingresso–target, regole), cinque tessere specialist (fatti vecchi e superati che arretrano ma restano leggibili), Storico decisioni, Lezioni, Note di Luca (composer `add_dossier_note`), Versioni. Firme: hover/pin su un autore illumina i suoi fatti. Telefono: ordine "decisione prima", indice sezioni sticky.
- **Link alla scheda.** Header del grafico (simbolo) e righe della watchlist nel Terminale; desk, coda e vista agente nell'Ufficio. Portafoglio: link da aggiungere quando il branch `portafoglio-frontend` sarà mergiato.
- **Stati onesti.** Caricamento, endpoint non esposto (nomina l'endpoint), scheda mancante (chiedi al PM di seguire il ticker), scheda vuota, nessun agente del ticker (affermato solo se la read della scheda esiste), fatti vecchi, proposta bloccata dal Risk Gate, Halt, Runtime irraggiungibile (scritture disabilitate).

## Adapter in attesa del backend (nomi del contratto, verbatim)

| Lettura/comando | File frontend | Stato senza backend |
|---|---|---|
| `GET /v1/read/agents` campi `kind`, `ticker`, `supervisor` | `features/office/api.ts` (`normalizeAgent`) | fallback dal prefisso `ticker:` del nome; desk "non esposto" |
| `GET /v1/read/dossier?ticker=` | `features/dossier/api.ts` `fetchDossier` | "Comparirà quando il Runtime esporrà GET /v1/read/dossier" |
| `GET /v1/read/dossier_history?ticker=&limit=` | `fetchDossierHistory` | tessera Versioni nomina l'endpoint |
| `GET /v1/read/proposals?status=&ticker=&limit=` | `fetchProposals` | coda nomina l'endpoint |
| `GET /v1/read/dossiers?limit=` | `fetchDossiers` | desk nomina l'endpoint |
| `add_dossier_note {ticker, text}` | `pages/ticker/tiles.tsx` `NotesTile` | rifiuto del Runtime mostrato verbatim |
| `decide_proposal {proposal_id, action, reason, confirm:true, sizing_fraction?, next_check_date?}` | `features/dossier/decide-proposal.tsx` | **payload proposto dal frontend**, vedi fondo di `handoff-backend.md` |
| SSE `dossier.updated`, `proposal.submitted`, `proposal.decided`, `agent.status` | `lib/runtime/sse.ts`, `provider.tsx` (`keysFor`) | invalidano dossier, dossier_history, dossiers, proposals, agenti |

## Sviluppo

- Fixture solo nel dev server: `COCKPIT_TICKER_FIXTURES=1` (12 ticker) o `=dense` (40), plugin `frontend/dev/ticker-fixtures.ts`; header `X-Dev-Fixture`. Non entrano nel build di produzione (verificato su `dist/`).
- Avvio: `COCKPIT_TICKER_FIXTURES=1 COCKPIT_PORT=5179 COCKPIT_RUNTIME_URL=http://127.0.0.1:8771 npx vite` da `frontend/`, Runtime sintetico `uv run python scripts/dev_cockpit_server.py --port 8771 --db data/dev-cockpit-ticker-fe.db`.
- Brief di superficie Impeccable copiati in `.scratch/ticker-agents/surfaces/`.
