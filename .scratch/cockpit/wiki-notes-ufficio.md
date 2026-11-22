# Note per il Wiki: Backend dell'Ufficio

Sintesi delle modifiche introdotte per l'Ufficio del cockpit (branch `worktree-backend-ufficio`):

## 1. Nuovi endpoint Read Model (`/v1/read`)
- `/v1/read/agents`: panoramica agenti configurati (`config/office.toml` e tabella `agents` in `OfficeDB`), con stato (`working`, `waiting`, `idle`), `current_task` (ticker e id ciclo/task), `last_activity_ts`, `today_tokens_in`, `today_tokens_out`, `today_tokens`, e `today_cost` calcolati da `llm_calls` per la giornata UTC corrente.
- `/v1/read/chat_topics?agent=`: elenco dei topic/canali dell'agente con `id` (chat_id), `topic`, `title`, eventuale `ticker` e `cycle_id`, `message_count`, `last_activity_ts`, e anteprima dell'ultimo messaggio.
- `/v1/read/tool_calls?agent=&cycle=&after=&limit=`: cronologia e stream delle invocazioni tool, con parametri, risultato, durata in ms, `success` (bool), eventuale `error`, `topic`, `cycle_id`, e flag esplicito `compacted: bool` (true se compattato dalla retention).
- `/v1/read/usage?agent=&from=&to=`: aggregazione delle chiamate LLM (`llm_calls`) per agente e periodo (timestamp ISO UTC), con token in/out, costo e conteggio chiamate.

## 2. Eventi Live SSE (`events` table)
Rispettato il modello single-writer: gli eventi nascono nella stessa transazione di scrittura del DB e vengono pubblicati sul bus in memoria su commit:
- `chat.message`: emesso su `OfficeDB.append_message` (da `say`, cicli o interazioni agenti) con dettagli completi (agente, topic, autore, testo, kind, ciclo, ts).
- `tool.called`: emesso su `OfficeDB.log_tool_call` (da `AgentEnvironment` o writer) con esito, durata e ciclo.
- `agent.status`: emesso su `OfficeDB.set_agent_status` con stato e task corrente.

## 3. Scenario di Sviluppo
- `scripts/dev_cockpit_scenario.py`: arricchito con agenti in stati differenti, chat multiple (incluse conversazioni con Luca e chat tematiche macro/semiconduttori), tool calls riuscite, fallite e compattate, storico chiamate LLM.
- `scripts/dev_cockpit_server.py`: aggiunto simulatore in background (`_live_event_simulator`) che emette periodicamente eventi SSE per mostrare lo stream animato in fase di sviluppo frontend.
