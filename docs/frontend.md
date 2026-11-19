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
- Clearly distinguish paper and live trading.
- Display connection and market-data freshness.
- Handle loading, empty, error and stale-data states.
- Make order execution and risk controls explicit.
- Never use mock data in production interfaces.

## Quality assurance
- Run Impeccable critique and audit.
- Verify layouts with Playwright.
- Capture screenshots at desktop and mobile sizes.
- Fix visual inconsistencies before completing tasks.