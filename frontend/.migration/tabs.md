# tabs

2026-11-24, transformation engine to Base UI, verified clean.

## Changed

- `src/components/ui/tabs.tsx` and `src/components/panel-tabs.tsx`: Migrated from `radix-ui` `Tabs` to `@base-ui/react/tabs`. Trigger -> Tab, Content -> Panel. Added `data-active` styling hooks to CSS and component classes.
- leftover scan: clean (0 matches).

## Left alone

None.

## Behavior changes

- Base UI defaults to manual tab activation unless configured with `activateOnFocus`.

## Verify by hand

- Click tabs in terminal dock (Ordini aperti / Eseguiti / Trade), portfolio panels, and office views.
- Confirm active tab styling lights up and panels switch correctly.
