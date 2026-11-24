# Assistente e mini Bridge: note per il wiki (frontend)

Branch `claude/assistente-frontend-ui-a54415`. Contratto vincolante: `handoff-backend.md`. Qui c'è cosa registrare nel wiki e cosa aspetta il backend.

## Cosa registrare nel wiki

- **Home del cockpit.** `/` e `/assistente` aprono l'Assistente: la conversazione di Luca con il Bridge. Le route sconosciute rimandano a `/`.
- **Layout desktop** (da 1024 px), come la vista agente dell'Ufficio:
  - a sinistra Conversazioni, al centro la conversazione, a destra Stato vivo;
  - Ctrl/⌘ B e Ctrl/⌘ Alt B chiudono i pannelli laterali; i separatori li ridimensionano.
- **Layout telefono:** la conversazione occupa tutto lo schermo, con il briefing compatto in alto. Conversazioni e Stato vivo si aprono come pannelli scorrevoli dall'intestazione.
- **Barre di riapertura** (`CollapsedRail`). Un pannello nascosto lascia una barra di 32 px con icona, nome e scorciatoia, che basta cliccare per riaprirlo. Vale per tutte le pagine con il layout dello shell:
  - Terminale: Watchlist, Attività, Ordini (con il numero di ordini da approvare);
  - Ufficio, vista agente: Agenti e chat, Tool;
  - Assistente.

  È una richiesta di Luca del 2026-11-23.
- **Briefing:**
  - su una conversazione nuova è un masthead completo: sintesi del Bridge, variazione del portafoglio, conteggi, sei voci con la gravità;
  - su una conversazione aperta si riduce a una riga che si espande sul posto (scelta di Luca);
  - "Chiedi al Bridge" su una voce manda la voce al Bridge con il riferimento come contesto;
  - "Segna come letto" chiama `mark_briefing_seen`.
- **Card azione:**
  - un'azione sul capitale proposta dal Bridge parte solo con Conferma, che invia `bridge_action_decide {action_id, decision:"confirm", confirm:true}`; Annulla invia `decision:"dismiss"`;
  - Conferma è disabilitata, e dice perché, se il Runtime è irraggiungibile, se c'è Halt sui comandi d'ordine, o se l'anteprima dice che il Risk Gate la rifiuterebbe;
  - i motivi del Risk Gate e del Runtime si mostrano così come arrivano;
  - la UI non distingue paper e live.
- **Mini Bridge:**
  - è il pannello Bridge dello shell, su tutte le pagine tranne l'Assistente, e mostra le stesse conversazioni;
  - il contesto della pagina si vede come tag rimovibile ("Contesto Terminale · AAPL") e accompagna ogni messaggio;
  - le fonti del contesto: Terminale `?t`, `/ticker/:symbol`, la posizione selezionata in Portafoglio (`usePageRef`), l'agente in `/ufficio/:agent`;
  - "Apri nell'Assistente" porta alla stessa conversazione a tutto schermo.
- **Fallback:** finché il Runtime non espone il Bridge, Assistente e mini Bridge dicono quale endpoint manca. Intanto si può scrivere a un agente con `@agente`, come prima: `say` nella chat «cockpit» dell'agente.
- **Colore autore:** `--author-bridge`, menta `oklch(0.85 0.085 168)`, avatar BR. Il Bridge non è in `AGENT_IDS`.
- **Fixture di sviluppo:** `COCKPIT_ASSISTANT_FIXTURES`, solo sul dev server di Vite. Le modalità si possono combinare con la virgola:
  - `1`: dati seminati;
  - `empty`: nessuna conversazione e briefing vuoto;
  - `slow`: le letture rispondono dopo 2,5 s;
  - `nobudget`: il Bridge ha esaurito il budget.

  Le fixture simulano anche gli eventi SSE di un turno: le parole «chiudi»/«riduci» producono un'azione, «budget» un errore, `@agente` una risposta inoltrata, e Stop interrompe il turno. Nell'intestazione compare il tag «Dati di esempio».

## Adattatori in attesa del backend

Tutti in `frontend/src/features/bridge/api.ts`, con i nomi esatti del contratto. Un 404 "not found" diventa lo stato `unavailable` con il nome dell'endpoint.

| Adattatore | Endpoint | Note |
|---|---|---|
| `fetchConversations` | `GET /v1/read/bridge_conversations?q&archived&limit` | stato di disponibilità del Bridge per tutta la UI |
| `fetchConversation` | `GET /v1/read/bridge_conversation?id&limit` | 404 con altro testo = conversazione inesistente (`missing`) |
| `fetchActions` | `GET /v1/read/bridge_actions?status` | pannello Stato vivo |
| `fetchBriefing` | `GET /v1/read/briefing?since` | masthead e riga compatta |

Comandi (`lib/runtime/types.ts`):

- `bridge_say {conversation_id|null, text, context|null}` → `data.conversation_id`, `data.message_id`;
- `bridge_stop {conversation_id}`;
- `bridge_rename_conversation {conversation_id, title}`;
- `bridge_archive_conversation {conversation_id, archived}`;
- `bridge_action_decide {action_id, decision, confirm}`;
- `mark_briefing_seen {ts}`.

Eventi SSE (registrati in `sse.ts` e invalidati in `provider.tsx`): `bridge.message`, `bridge.status` (`{conversation_id, status: thinking|tool|idle, tool}`, guida la riga del turno in corso), `bridge.action`, `bridge.conversation`, `briefing.updated`, `tool.finished`.

## Cose da verificare quando arriva il backend

- `bridge.status` deve portare `conversation_id` e `tool`: senza, la riga «Il Bridge usa …» non compare.
- L'azione dentro il messaggio (`message.action`) deve avere `preview.ok` e `preview.reasons`: Conferma si disabilita su `preview.ok === false`.
- `last_message` nel riepilogo della conversazione: per i messaggi-azione senza testo la UI mostra il `summary` dell'azione, quindi il backend può lasciare il testo vuoto.
- Il 404 di una conversazione inesistente non deve contenere "Read endpoint … not found", altrimenti viene letto come Bridge non disponibile.

## Verifica fatta

- `npx tsc -b --noEmit` e `npm run build` verdi.
- Playwright a 1440×900 e 390×844 su ogni stato: caricamento, nessuna conversazione, briefing vuoto, turno in corso con tool, risposta inoltrata, azione da confermare / eseguita / rifiutata dal Risk Gate / annullata, errore di budget, Halt, Runtime irraggiungibile, endpoint del Bridge non esposto, pannelli chiusi con barre di riapertura, mini Bridge su Terminale e telefono.
- Impeccable:
  - `detect` senza risultati;
  - `first-viewport` ok su contenuto principale e azione principale;
  - finish review fatta in questa sessione con la procedura degradata, perché i subagenti Sonnet e Haiku hanno risposto «model not found»;
  - correzioni applicate: testo introduttivo di una riga sotto il briefing completo, «n agenti in attesa», nomi degli agenti nelle fixture;
  - audit leggero: pannello espanso chiuso reso `inert`, target touch ≥ 24 px.
