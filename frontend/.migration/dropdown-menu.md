# dropdown-menu

2026-11-24, transformation engine to Base UI, verified clean.

## Changed

- `src/components/ui/dropdown-menu.tsx`: Migrated from `radix-ui` `DropdownMenu` to `@base-ui/react/menu`. Restructured Content into `Portal > Positioner > Popup`. Replaced `Item`, `GroupLabel`, `CheckboxItem`, `RadioItem`, `SubmenuRoot`, and `SubmenuTrigger`.
- leftover scan: clean (0 matches).

## Left alone

None.

## Behavior changes

None.

## Verify by hand

- Click AccountSwitcher or table row actions.
- Confirm keyboard arrow navigation, enter/escape behavior, and item selection.
