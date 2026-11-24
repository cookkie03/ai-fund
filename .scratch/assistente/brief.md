# Brief: pagina Assistente e Bridge agent

Decisioni di Luca del 2026-11-23, che completano quella del 2026-11-20 (wiki `system/interface/frontend-module.md`, sezione «Pagine del cockpit»). Branch della pagina: **`assistente-frontend`** (backend e frontend insieme, PR verso `main` con CI verde).

## Cosa è

L'Assistente è la **home** del cockpit (`/`, oggi reindirizza al Terminale; anche `/assistente`). È il posto dove Luca parla in linguaggio naturale con il **Bridge agent**, un pari di Luca dentro l'ufficio: legge tutto, parla con ogni agente e usa gli stessi comandi della UI. Il motore resta autonomo al 100%: il Bridge non è una coda di approvazioni, è il collega a cui Luca chiede «cosa è successo», «perché il PM ha rifiutato NVDA», «chiedi al Technical di rivedere i livelli di AMD», «riduci MSFT di metà».

## Decisioni

1. **Il Bridge si costruisce adesso**, nel Runtime: agente vero (`bridge`), con i suoi tool, costi e budget come gli altri. Supera il «UI ora, agente dopo» del 2026-11-20.
2. **Home a tre zone insieme:**
   - **Briefing** in alto: cosa è successo dall'ultima visita (trade eseguiti, proposte in attesa del PM e decise, alert, Halt, variazione del portafoglio, schede cambiate, errori degli agenti), con una sintesi scritta dal Bridge. Ogni voce si può chiedere al Bridge («spiegami questo»).
   - **Conversazione** al centro.
   - **Pannello laterale** con lo stato vivo: portafoglio (valore, P&L di oggi, cassa), ufficio (agenti al lavoro, proposte in attesa), Halt e connessione.
3. **Più conversazioni**, come l'app di Claude: elenco a sinistra, nuova conversazione per argomento, ricerca, rinomina, archivio.
4. **Mini Bridge ovunque:** il pannello Bridge dello shell (già presente su ogni pagina) diventa la stessa conversazione dell'Assistente, e passa al Bridge il contesto della pagina aperta (pagina, ticker, posizione, proposta).

## Regole che non cambiano

- Runtime unico writer, SQLite fonte di verità, comandi con `Idempotency-Key` e `X-Actor`, eventi nella stessa transazione.
- Il **Risk Gate è sovrano**. Tutto ciò che tocca capitale (approvare ordini, chiudere o ridurre posizioni, modificare stop e target, decidere proposte, Halt/Resume, limiti di rischio) il Bridge lo **propone come azione** e lo esegue solo dopo la conferma esplicita di Luca nella UI (`confirm:true`), passando dallo stesso handler del comando originale. Le azioni senza capitale (watchlist, note nella scheda, messaggi agli agenti, task, refresh dati, annotazioni) il Bridge le esegue da sé e lo dice.
- Il parere di Luca (anche tramite Bridge) è un'opinione che gli agenti pesano, non un ordine: il ticker propone, il PM decide.
- Nessuna distinzione paper/live nella UI.

## Fuori scope ora

Memoria a lungo termine delle preferenze di Luca, voce, notifiche push, Bridge su Telegram, pagina Notizie e Configurazioni.
