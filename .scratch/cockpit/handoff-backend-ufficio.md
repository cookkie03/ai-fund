# Handoff: backend del Runtime per l'Ufficio del cockpit

Repo `/home/luca/trading-agent`, branch di partenza `feat/cockpit-frontend` (ex `docs/agent-restart`). Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: test verdi, ruff pulito, `graphify update .`, commit e push sul tuo branch.

## Perché

La prossima pagina del cockpit è l'Ufficio (`.scratch/cockpit/brief-ufficio.md`): panoramica degli agenti, più chat per agente, stream dal vivo delle chiamate ai tool, costi e token. Il frontend legge e scrive passando dal Runtime come gli agenti ("collega jolly"). API attuale: `docs/dashboard.md`. Architettura: `docs/adr/0003-runtime-unico-writer-event-driven.md`. Le tabelle `llm_calls` e `tool_calls` esistono già in `storage/office_db.py` (scritte via `storage/registry.py`), ma non sono esposte.

## Cosa fare (test-first, skill `tdd`)

1. **Agenti**: `GET /v1/read/agents`: per ogni agente configurato (`config/office.toml`) nome, ruolo, modello, stato (`working` / `waiting` / `idle`), task o ciclo corrente con ticker, ultima attività (timestamp), costo e token di oggi.
2. **Chat per agente**: `GET /v1/read/chat_topics?agent=` con i topic di quell'agente (id, titolo leggibile, ticker o ciclo se presenti, ultimo messaggio, timestamp, numero di messaggi). Verifica che `/v1/read/chat?agent=&topic=` e il comando `say` coprano già leggere e scrivere su un topic specifico; se manca qualcosa, aggiungilo.
3. **Chiamate ai tool**: `GET /v1/read/tool_calls?agent=&cycle=&after=&limit=`: tool, argomenti, risultato, durata, esito, errore, timestamp, ciclo e topic se noti. Se la retention ha compattato input o output, un campo esplicito lo dice (non `null` silenzioso).
4. **Uso e costi**: `GET /v1/read/usage?agent=&from=&to=` aggregato da `llm_calls` (token in e out, costo, numero di chiamate) per agente e periodo.
5. **Eventi SSE dal vivo**, nella tabella `events`: `chat.message`, `tool.called` (con esito e durata; se utile anche un evento di inizio), `agent.status`. Rispetta il modello single-writer: gli eventi nascono quando il Runtime registra davvero il dato, non da polling. Controlla come il buffer di `storage/registry.py` scrive e scegli il punto giusto.
6. **Scenario di sviluppo**: estendi `scripts/dev_cockpit_scenario.py` (e `scripts/dev_cockpit_server.py`) con agenti in stati diversi, più chat per agente con messaggi di agenti e di Luca, chiamate ai tool riuscite, fallite e compattate, uso e costi, e qualche evento dal vivo periodico così il frontend vede lo stream muoversi. Mai usato in produzione.
7. Aggiorna `docs/dashboard.md` (endpoint, eventi).

## Fuori scope

Bridge agent, pausa degli agenti, sezione Evaluation completa, CORS (il frontend usa il proxy di Vite), modifiche a `frontend/`.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere i sorgenti.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo con `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non committare `data/*.db*`, `nohup.out`, `.serena/`, `graphify-out/` (salvo il grafo se già tracciato), `frontend/tsconfig.tsbuildinfo`.
- Lavori in un worktree: un'altra sessione costruisce in parallelo la pagina Ufficio in `frontend/`; non toccare `frontend/`. Non fare push su `feat/cockpit-frontend`: l'unione la decide Luca.
