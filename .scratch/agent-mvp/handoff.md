# Handoff: chiudere la spec "ufficio di agenti di trading" (MVP)

## Goal (da impostare con `/goal`)

```
/goal Completare .scratch/agent-mvp/spec.md nel repo /home/luca/trading-agent: chiudere i 9 gap elencati in "Gap residui" (verificandoli prima nel codice), con test, motore ridistribuito via Docker Compose e verificato con un ciclo reale; aggiornare il wiki (/home/luca/trading-agent-wiki, log + board); commit e push di entrambi i repo. Delega a `claude -p --model my-combo` i lavori circoscritti dove possibile.
```

Il Goal è finito quando: tutti i punti di "Definizione di fatto" sono veri e li hai verificati con comandi, non a memoria.

## Contesto (stato al 2026-11-19)

Repo: `/home/luca/trading-agent`, branch `docs/agent-restart` (pushato, working tree pulito salvo file untracked non da committare: `.serena/`, `data/trading-agent.db*`, `graphify-out/`, `nohup.out`, `frontend/tsconfig.tsbuildinfo`). Wiki: `/home/luca/trading-agent-wiki` (log in `wiki/_meta/log.md`, board in `wiki/artifacts/project-board`).

Già fatto e verificato (247 test passati, 2 skipped):
- Motore Python con sei agenti pari (PM + Market/Sentiment/Technical/Fundamental/Risk), Scheduled task, cicli, budget, Rimando, Risk Gate, coda approvazioni, bracket order, trailing, registro LLM/tool, cache dati DB-first (Yahoo, Alpaca news, OpenBB opzionale via `DATA_PRICES_PROVIDER`), CLI `trading-agent`.
- Deploy in produzione su questo host (Debian, è il "Minisforum"): `docker compose -f compose.engine.yaml up -d --build`, servizio `engine`, endpoint LLM `OFFICE_LLM_ENDPOINT=http://omniroute:20128/v1` sulla rete `omniroute_default`.
- Ordine bracket reale su Alpaca paper inviato e cancellato; sync stato ordini dal broker (`orders sync`, ogni 30 s).
- Prototipo legacy rimosso (sqlite.py, dashboard, scripts, compose.yaml vecchio). Restano `frontend/`, `openbb-ui/`, `telegram-claude/` (app separate, non toccare).
- Prompt in `prompts/*.md` (bozze per la revisione di Luca: lascia il marker "DRAFT per la revisione di Luca").

## Gap residui (da un audit automatico: VERIFICA OGNUNO nel codice prima di lavorarci)

Audit: 117 storie implementate, 6 parziali, 3 mancanti.

| US | Gap | Dove |
|---|---|---|
| 12 | Handler che trasforma allarmi esterni (prezzo/calendario/utili) in Scheduled task immediati | `workflows/scheduling.py`, `workflows/office.py` |
| 16 | Attivazioni fisse del Market Analyst (pre-market, eventi del calendario macro) generate dallo scheduler | `workflows/office.py` |
| 62 | Rifiuto manuale di un ordine non scrive il Rimando con motivo nella chat del PM | `execution/order_flow.py` |
| 77 | Il Market Analyst non ha un tool per scrivere la vista di settore nello stato | `tools/environment.py` |
| 85 | `portfolio_risk` non calcola la correlazione di portafoglio | `tools/environment.py` |
| 89 | Pre-fetch watchlist/portafoglio (`refresh_watchlist_and_portfolio`) non è eseguito periodicamente nel loop | `workflows/office.py` |
| 101 | Job settimanale di retention/downsampling + incremental vacuum non cablato | `storage/retention.py`, `workflows/office.py` |
| 102 | Allarme in Inbox quando `db_size_bytes()` supera `db_size_alert_mb` | `storage/office_db.py`, `workflows/office.py` |
| 117 | Inbox senza avvisi sulla dimensione del DB (stessa causa di 102) | idem |

Se un gap risulta già coperto, scrivilo nel log wiki con la prova (file + test) e passa oltre. Se la spec e il codice divergono su un punto ambiguo, scegli l'interpretazione più semplice coerente con la spec e annotala nel log; non fermarti a chiedere.

Nota di priorità: 62, 102/117, 101, 89 sono piccoli e a basso rischio. 12, 16, 77, 85 sono più grandi: implementali nella forma minima che soddisfa la storia nella spec (leggila), non estenderli.

## Regole non negoziabili

- Il modello `free` di OmniRoute NON va MAI usato (nemmeno per sottotask). Se deleghi, solo `claude -p --model my-combo` con una brief autocontenuta; verifica sempre il diff del delegato.
- Non stampare né committare segreti (`.env`, `OMNIROUTE_API_KEY`, chiavi Alpaca). Il `.env` del progetto è privato.
- Alpaca è **paper**: ordini reali di prova sono autorizzati da Luca, ma cancellali dopo e non lasciare posizioni/ordini aperti.
- Risposte concise, azione prima della spiegazione. Codice **e** wiki sempre sincronizzati, con commit e push di entrambi.
- Non usare `git add -A` alla cieca nel repo: escludi i file untracked elencati sopra. Messaggi di commit in stile convenzionale (`fix(...)`, `feat(...)`).
- Navigazione codice: prima `graphify query "<domanda>"` (esiste `graphify-out/`), poi lettura mirata. Dopo modifiche al codice: `graphify update .`.

## Come lavorare e verificare

Test e lint (devono restare verdi; nessun `# noqa`):

```bash
cd /home/luca/trading-agent && uv run pytest -q
uv run ruff check execution tools workflows storage bootstrap.py interface agents data analysis
```

Deploy e CLI nel container:

```bash
docker compose -f compose.engine.yaml up -d --build
E="docker compose -f compose.engine.yaml exec -T engine uv run --no-sync trading-agent"
$E task AAPL --reason "Valuta un ingresso long su AAPL"   # accoda un ciclo reale (LLM my-combo, dati live, Alpaca paper)
$E cycles list; $E orders list; $E inbox; $E orders sync
```

Aspetta i cicli con un loop `until`/Monitor, non con `sleep` lunghi in foreground (un ciclo reale dura 30 s – 4 min).

Smoke test reale opt-in (broker finto): `OMNIROUTE_API_KEY=... uv run pytest tests/integration/test_office_smoke.py -m integration -q -s` (la chiave si legge da `/home/luca/.claude/.env`, mai stamparla).

Buone pratiche già validate in questo progetto:
- Ogni bug trovato in produzione ottiene un test di regressione che fallisce senza la correzione.
- I prezzi di ordine sono arrotondati al centesimo; l'errore del broker marca l'ordine `rejected` e il ciclo chiude in "rimando".
- Il PM deve consultare gli Analyst prima di decidere; non indebolire questa guardia.

## Definizione di fatto

1. Ognuno dei 9 gap è chiuso con test automatico (o documentato come già coperto con la prova).
2. `uv run pytest -q` tutto verde, ruff pulito sui percorsi sopra.
3. Motore ricostruito e in esecuzione (`docker compose -f compose.engine.yaml ps` mostra `engine` Up) e almeno un ciclo reale completato dopo le modifiche, senza errori nel log del container.
4. Nessun ordine o posizione aperti su Alpaca paper (`$E orders sync` poi `$E orders list`).
5. Wiki aggiornato (`wiki/_meta/log.md` con una voce per ogni blocco di lavoro, e la board), repo codice e wiki committati e pushati (`git status -sb` senza avanti/indietro).
6. Report finale breve a Luca: cosa è chiuso, cosa no e perché, e il ricordo che i prompt in `prompts/` restano bozze da rivedere.
