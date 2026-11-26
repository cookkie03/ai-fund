import { cn } from "cn"

/** The AI Fund monogram: "AF" knocked out of a primary rounded square. Monochrome, follows the theme. */
export function AfMark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-[13px] font-semibold tracking-[-0.04em] text-primary-foreground", className)} aria-label="AI Fund">
      AF
    </span>
  )
}
