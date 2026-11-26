import { CheckIcon, ClockIcon, XIcon, CircleSlashIcon, TriangleAlertIcon } from "lucide-react"
import { Badge } from "@/ds/ui/badge"
import { cn } from "cn"

export type OrderState = "pending" | "filled" | "rejected" | "cancelled" | "stale"

const MAP: Record<OrderState, { label: string; icon: typeof CheckIcon; cls: string }> = {
  pending: { label: "Pending approval", icon: ClockIcon, cls: "bg-warning/15 text-warning" },
  filled: { label: "Filled", icon: CheckIcon, cls: "bg-success/15 text-success" },
  rejected: { label: "Rejected", icon: XIcon, cls: "bg-destructive/10 text-destructive" },
  cancelled: { label: "Cancelled", icon: CircleSlashIcon, cls: "bg-muted text-muted-foreground" },
  stale: { label: "Stale data", icon: TriangleAlertIcon, cls: "bg-warning/15 text-warning" },
}

/** Icon + word on a soft tint. The only place state colours (success, warning, destructive) fill a surface. */
export function StatusBadge({ state, label, className }: { state: OrderState; label?: string; className?: string }) {
  const m = MAP[state]
  const Icon = m.icon
  return (
    <Badge variant="secondary" className={cn("gap-1 border-transparent", m.cls, className)}>
      <Icon aria-hidden />
      {label ?? m.label}
    </Badge>
  )
}
