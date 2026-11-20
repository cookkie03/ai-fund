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
Cinque pagine, un solo design system. Dettaglio in `PRODUCT.md`.
1. **Assistente** (home): chat con il Bridge agent, pari dell'utente.
2. **Ufficio**: agenti, loro chat (lettura e scrittura) e stream dei tool chiamati.
3. **Terminale**: grafico (lightweight-charts) con i disegni di agenti e utente condivisi, quote/order book, ordini aperti e pendenti, agenti attivi sullo strumento, watchlist condivisa e modificabile.
4. **Portafoglio**: statistiche, esposizione, allocazione, posizioni, trade; metriche e vincoli di rischio che il portafoglio deve rispettare.
5. **Configurazioni**: agenti, modelli, prompt, schedule, budget, provider, account, DB, salute del Runtime.

Direzione visiva: lo standard di ogni genere (terminale finanziario, app bancaria desktop, chat assistente, workspace agenti) eseguito al livello dei migliori prodotti, senza metafore. L'input dell'utente è un parere che gli agenti pesano; il Risk Gate resta sovrano.

## Workflow Impeccable
1. `shape`: un brief per pagina (job, dati reali dal Runtime, stati, interazioni), in `.impeccable/` come surface brief.
2. Riferimenti: due o tre prodotti per genere fissano il livello di qualità; niente giro di direzioni con metafore.
3. Sistema condiviso: shell, token e componenti shadcn una volta sola, poi le pagine.
4. Build in codice pagina per pagina (le superfici operative sono code-led), con i gap di backend chiusi prima della pagina che li usa.
5. Per ogni pagina: `critique`, `audit`, screenshot Playwright desktop e mobile, finish review.
6. A fine build: `DESIGN.md` dal codice costruito (documenter).
