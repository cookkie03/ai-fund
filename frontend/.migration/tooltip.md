# tooltip

2026-11-24, transformation engine to Base UI, verified clean.

## Changed

- `src/components/ui/tooltip.tsx`: Migrated from `radix-ui` `Tooltip` to `@base-ui/react/tooltip`. Converted to `Portal > Positioner > Popup`. Replaced `delayDuration` with `delay`.
- leftover scan: clean (0 matches).

## Left alone

None.

## Behavior changes

None.

## Verify by hand

- Hover over icons in the navigation rail, top bar, and metrics.
- Confirm tooltip pops up with correct side and offset.
