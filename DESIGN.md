# Design: AI Fund Design System

The UI follows the **AI Fund Design System**. Full rules: [`docs/design-system/README.md`](docs/design-system/README.md); every decision: [`DECISIONS.md`](docs/design-system/DECISIONS.md); folder rules: [`ARCHITECTURE.md`](docs/design-system/ARCHITECTURE.md); tokens: [`tokens.json`](docs/design-system/tokens.json). Live reference with previews: the "AI Fund Design System" artifact on claude.ai. The previous cockpit design is archived in `docs/design-system/legacy-DESIGN-cockpit-v1.md`.

In short:

- **A banking app with a professional engine** (Revolut / Trade Republic): one job per page, details on demand (Sheet, Tabs, Dialog), one card per object.
- **Vanilla shadcn/ui on Base UI** (`base-vega`), no Radix. Everything visual lives in `frontend/src/ds/`; pages import from `@/ds` and only lay out.
- **Monochrome neutral**, light (default) + dark. Colour only for direction (`success` / `destructive`, always with sign or arrow) and attention (`warning`). Charts in grays; **the TradingView chart is never restyled**.
- One author sign: `AgentAvatar` (gray initials circle). English UI. Inter, radius 14 px, Lucide icons.
- **Motion everywhere, gently**: reveal, count-up, price flash, hover lift; reduced motion keeps only the flash.
