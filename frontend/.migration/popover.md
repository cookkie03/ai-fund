# popover

2026-11-24, transformation engine to Base UI, verified clean.

## Changed

- `src/components/ui/popover.tsx`: Migrated from `radix-ui` `Popover` to `@base-ui/react/popover`. Replaced Content with `Portal > Positioner > Popup`.
- `src/pages/ufficio/assign-task.tsx`: Button element passed directly to `PopoverTrigger` via `render={button}`, preserving native `<button>` semantics.
- leftover scan: clean (0 matches).

## Left alone

None.

## Behavior changes

- `onOpenAutoFocus` replaced by Base UI `initialFocus` ref property.

## Verify by hand

- Open Inbox popover, watchlist ticker add popover, and assign task popover.
- Verify positioning, autofocus on inputs, and outside click dismissal.
