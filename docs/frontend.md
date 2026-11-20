# Frontend Design Rules

## Design authority
- Impeccable is the primary design authority.
- Figma is the source of approved design references.
- 21st.dev is the component discovery library.
- shadcn/ui is the foundational component system.
- Taste is used for visual exploration, not as a
  mandatory style for operational screens.

## Product design
- Design a professional trading terminal.
- Prioritize information density and readability.
- Use tabular numerals for financial values.
- Use consistent colors for PnL and order status.
- Minimize unnecessary animations.
- Support responsive layouts and keyboard navigation.
- Avoid generic SaaS dashboard aesthetics.

## Trading-specific UX
- Always show the active broker account; accounts are selectable.
- Never expose a paper/live mode: an account is paper or live only by its
  credentials (see PRODUCT.md).
- Display connection and market-data freshness.
- Handle loading, empty, error and stale-data states.
- Make order execution and risk controls explicit.
- Never use mock data in production interfaces.

## Quality assurance
- Run Impeccable critique and audit.
- Verify layouts with Playwright.
- Capture screenshots at desktop and mobile sizes.
- Fix visual inconsistencies before completing tasks.
## Pagine del cockpit (decise il 2026-11-20)
Sei pagine, un solo design system. Dettaglio in `PRODUCT.md`. L'idea del **collega jolly** pervade tutta la UI: l'utente lavora sullo stesso materiale degli agenti, con le stesse letture e scritture via Runtime.
1. **Assistente** (home): chat con il Bridge agent, pari dell'utente. Si progetta ora la UI/UX; l'agente si implementa dopo nel Runtime.
2. **Ufficio**: agenti, loro chat (lettura e scrittura) e stream dei tool chiamati.
3. **Terminale**: pagina moderna e densa su TradingView lightweight-charts, ambiente principale del Technical Analyst: prezzo, volumi, indicatori e disegni condivisi agenti/utente; ordini aperti e pendenti; agenti attivi sullo strumento; watchlist condivisa e modificabile. Niente order book.
4. **Notizie**: l'ambiente news degli agenti, con gli stessi tool: leggere, filtrare, selezionare e inviare notizie agli agenti.
5. **Portafoglio**: statistiche, esposizione, allocazione, posizioni, trade; metriche e vincoli di rischio che il portafoglio deve rispettare.
6. **Configurazioni**: agenti, modelli, prompt, schedule, budget, provider, account, DB, salute del Runtime.

Direzione visiva: lo standard di ogni genere eseguito al livello dei migliori prodotti, componenti moderni e belli da applicazione professionale, senza metafore. L'input dell'utente è un parere che gli agenti pesano; il Risk Gate resta sovrano.

## Workflow Impeccable
1. `shape`: un brief per pagina (job, dati reali dal Runtime, stati, interazioni), in `.impeccable/` come surface brief.
2. Riferimenti di qualità (non da copiare): Terminale come TradingView e IBKR TWS; Assistente e Ufficio come app di Claude, Linear e Slack; Portafoglio professionale nelle informazioni e moderno nell'uso (Revolut, Trade Republic, ma più densi). Niente giro di direzioni con metafore.
   Ordine: shell comune + Terminale per primi.
3. Sistema condiviso: shell, token e componenti shadcn una volta sola, poi le pagine.
4. Build in codice pagina per pagina (le superfici operative sono code-led), con i gap di backend chiusi prima della pagina che li usa.
5. Per ogni pagina: `critique`, `audit`, screenshot Playwright desktop e mobile, finish review.
6. A fine build: `DESIGN.md` dal codice costruito (documenter).
