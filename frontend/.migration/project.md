# Full Project Migration: Radix UI -> Base UI (@base-ui/react)

2026-11-24, full project migration to official shadcn Base UI primitives, complete success.

## Dependency swap

- Removed `radix-ui` from `package.json` and `node_modules` (uninstalled 45 transitive radix packages).
- Removed `cmdk` and unused Command component, completely eliminating transitive `@radix-ui/react-dialog` and `@radix-ui/primitive` from `package-lock.json`.
- Added `@base-ui/react` (v1.9.0+).
- Updated `components.json` to `"base": "base"` and `"style": "base-nova"`.
- 0 references to `radix-ui` or `@radix-ui/*` remain in code or lockfile.

## Components migrated

1. `button.tsx` -> `@base-ui/react/button` (`Button as ButtonPrimitive` with `render` support)
2. `separator.tsx` -> `@base-ui/react/separator` (`Separator as SeparatorPrimitive`)
3. `tooltip.tsx` -> `@base-ui/react/tooltip` (Portal > Positioner > Popup architecture)
4. `dialog.tsx` -> `@base-ui/react/dialog` (Portal > Backdrop + Popup architecture)
5. `sheet.tsx` -> `@base-ui/react/dialog` (Side drawer panels with Base UI Backdrop + Popup)
6. `alert-dialog.tsx` -> `@base-ui/react/alert-dialog` (Backdrop + Popup + Close)
7. `popover.tsx` -> `@base-ui/react/popover` (Positioner + Popup)
8. `dropdown-menu.tsx` -> `@base-ui/react/menu` (Positioner + Popup + Items)
9. `scroll-area.tsx` -> `@base-ui/react/scroll-area` (Viewport > Content + Scrollbar + Thumb)
10. `toggle.tsx` -> `@base-ui/react/toggle` (Callable `Toggle` with `data-pressed`)
11. `toggle-group.tsx` -> `@base-ui/react/toggle-group` (Group + `Toggle` items, normalized array values)
12. `tabs.tsx` -> `@base-ui/react/tabs` (Root > List > Tab > Panel with `data-active`)
13. `panel-tabs.tsx` -> `@base-ui/react/tabs` (Tab + Panel with `data-active` & `data-hidden`)

## New shadcn UI components added

1. `card.tsx` (Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter)
2. `badge.tsx` (Badge, badgeVariants)
3. `table.tsx` (Table, TableHeader, TableBody, TableFooter, TableHead, TableRow, TableCell, TableCaption)

## App code consumer sweep

- Replaced all legacy `asChild` invocations with Base UI's canonical `render` prop (`TooltipTrigger`, `PopoverTrigger`, `DialogTrigger`, `DropdownMenuTrigger`, `DropdownMenuItem`, `Button`).
- Passed real button elements directly to `DialogTrigger` and `PopoverTrigger` `render` prop in `decide-proposal.tsx` and `assign-task.tsx`, preserving native `<button>` semantics.
- Converted `onOpenAutoFocus` on `PopoverContent` to `initialFocus={tickerRef}`.
- Configured `<MotionConfig reducedMotion="user">` in `src/App.tsx` for global declarative motion accessibility.
- Replaced manual status tags with official shadcn `Badge`.

## Verification

- `npm run typecheck`: clean (0 errors)
- `npm run build`: built in < 1s (0 warnings)
- Remaining wrappers on Radix: 0
