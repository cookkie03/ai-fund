# dialog

2026-11-24, transformation engine to Base UI, verified clean.

## Changed

- `src/components/ui/dialog.tsx`: Migrated from `radix-ui` `Dialog` to `@base-ui/react/dialog`. Overlay -> Backdrop, Content -> Popup, Close and Trigger support `render`.
- `src/features/dossier/decide-proposal.tsx`: Trigger element passed directly to `DialogTrigger` via `render={trigger}`, preserving native `<button>` semantics.
- leftover scan: clean (0 matches).

## Left alone

None.

## Behavior changes

None.

## Verify by hand

- Open Halt dialog or order decision dialog.
- Confirm backdrop blur/dim, Escape to close, outside click to close, and focus restoration.
