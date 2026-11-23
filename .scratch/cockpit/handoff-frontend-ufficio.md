# Handoff: pagina Ufficio del cockpit (Impeccable, code-led)

Repo `/home/luca/trading-agent`, branch di partenza `feat/cockpit-frontend` (ex `docs/agent-restart`, contiene shell e Terminale in stile Legend). Rispondi in italiano, conciso, azione prima della spiegazione. A fine lavoro: commit e push sul tuo branch (non su `feat/cockpit-frontend`: l'unione la decide Luca).

## Da leggere prima

`PRODUCT.md`, `docs/frontend.md` (regole vincolanti, sezioni sulla rifinitura e sullo stile Legend), `.scratch/cockpit/brief-ufficio.md` (brief confermato da Luca), `DESIGN.md` e `.impeccable/design.json` (sistema Legend già approvato), `docs/dashboard.md` (API del Runtime), il codice di shell e Terminale in `frontend/src/`.

## Ambiente: leggere bene

Claude gira su un PC Linux headless (`192.168.68.107`, utente `luca`); Luca usa l'app Claude su un MacBook. **Luca vuole l'esperienza Impeccable completa.** Ogni pagina da aprire va servita qui (per Impeccable `IMPECCABLE_QUESTION_FORCE=1`) e a Luca va dato il comando da lanciare sul Mac:

```bash
ssh -N -L 5174:127.0.0.1:5174 luca@192.168.68.107
```

poi `open http://127.0.0.1:5174/ufficio`. Dev server con dati finti: `uv run python scripts/dev_cockpit_server.py --port 8766 --db data/dev-cockpit-ufficio.db`, Vite sulla 5174 con proxy verso 8766.

## Decisioni già prese (non rimetterle in discussione)

- Mode **Operate**, build **code-led**, mondo **Legend** esistente: estendi il sistema di `DESIGN.md`, niente nuove direzioni. Riferimenti: app di Claude, Slack, Linear.
- Struttura: panoramica dell'ufficio, poi vista agente a tre zone (agenti e loro **più chat**, conversazione, stream dei tool con blocchi espandibili). Azioni: scrivere (`say` sul topic), assegnare un task (`enqueue_task`), costi e token per agente. Dettagli nel brief.
- Il collega jolly: Luca legge e scrive gli stessi ambienti degli agenti via Runtime; ogni messaggio mostra il suo autore.
- Stack e componenti già presenti in `frontend/`: riusa shell, client tipizzato di `/v1`, SSE con replay, stati, scorciatoie e layout ridimensionabile del Terminale.

## Flusso Impeccable

1. `.claude/skills/impeccable/scripts/impeccable context --target frontend/src` una volta, poi `reference/new-work.md` per una nuova superficie in un mondo esistente; surface brief dell'Ufficio con `impeccable surface-brief write`.
2. Leggi `reference/craft-floor.md` prima di ogni modifica UI.
3. Costruisci panoramica, vista agente, stream dei tool, azioni e tutti gli stati del brief, desktop e 390 px.
4. Verifica: `impeccable first-viewport ... --capture .impeccable/review` (desktop e 390 px), `impeccable detect`, screenshot Playwright, poi finish review, `/impeccable critique` e `/impeccable audit` e aggiornamento di `DESIGN.md`. Se i subagenti non rispondono, esegui le valutazioni inline secondo le rubric.

## Dipendenze dal backend

Un'altra sessione aggiunge al Runtime `agents`, `chat_topics`, `tool_calls`, `usage`, gli eventi SSE `chat.message`, `tool.called`, `agent.status` e lo scenario di sviluppo (`.scratch/cockpit/handoff-backend-ufficio.md`). Finché non è sul tuo branch: costruisci con gli endpoint esistenti (`chat`, `say`, `enqueue_task`, `cycles`, `cycle`) e metti i dati mancanti dietro adattatori tipizzati con i contratti del handoff backend; niente dati inventati in produzione. Quando il branch del backend è pronto, chiedi a Luca se unirlo.

## Note operative

- graphify: `graphify query "<domanda>"` prima di leggere sorgenti; `graphify update .` dopo modifiche al codice.
- Ignora `openbb-ui/` e `telegram-claude/`.
- Deleghe `claude -p`: solo con `~/.local/bin/claude-my-combo`, mai `free`. Subagenti solo Sonnet o Haiku.
- Non toccare il backend (`runtime/`, `storage/`, `scripts/`): lo fa l'altra sessione.
- Wiki e docs le aggiorna la sessione principale: annota in `.scratch/cockpit/wiki-notes-ufficio.md` cosa andrebbe registrato.
