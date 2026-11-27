import type { ReactNode } from "react"
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "@/ds/ui/card"
import { Delta } from "@/ds/identity/delta"
import { AnimatedNumber } from "@/ds/motion"

export const money = (v: number, currency = "$") => `${v < 0 ? "\u2212" : ""}${currency}${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

/** One figure, one label, one change: the banking-style balance card used in overview rows. */
export function StatCard({
  label,
  value,
  delta,
  deltaKind = "percent",
  footer,
  className,
}: {
  label: string
  /** A number counts up and is formatted as money; a string is shown as given. */
  value: string | number
  delta?: number
  deltaKind?: "percent" | "amount"
  footer?: ReactNode
  className?: string
}) {
  return (
    <Card className={className ? `ds-reveal ${className}` : "ds-reveal"}>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl font-semibold tabular-nums">{typeof value === "number" ? <AnimatedNumber value={value} format={(v) => money(v)} /> : value}</CardTitle>
        {delta !== undefined && <Delta value={delta} kind={deltaKind} className="text-sm" />}
      </CardHeader>
      {footer && <CardFooter className="text-sm text-muted-foreground">{footer}</CardFooter>}
    </Card>
  )
}
