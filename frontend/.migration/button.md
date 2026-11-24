# button

2026-11-24, transformation engine to Base UI, verified clean.

## Changed

- `src/components/ui/button.tsx`: Migrated from `radix-ui` `Slot` to `@base-ui/react/button` (`ButtonPrimitive`). Added native `render` and backward-compatible `asChild` prop resolution.
- leftover scan: clean (0 matches).

## Left alone

None.

## Behavior changes

None.

## Verify by hand

- Click buttons in top bar, watchlist, and dialogs.
- Confirm hover, active scale (0.97), and focus-visible outlines.
