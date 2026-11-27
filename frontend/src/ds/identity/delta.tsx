import { ArrowDownRightIcon, ArrowUpRightIcon, MinusIcon } from "lucide-react"
import { cn } from "cn"

const fmt = (v: number, kind: "percent" | "amount", currency: string) =>
  kind === "percent"
    ? `${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
    : `${currency}${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

/** A signed change: arrow + sign + value, green when up, red when down, gray when flat. Never colour alone. */
export function Delta({
  value,
  kind = "percent",
  currency = "$",
  className,
}: {
  value: number
  kind?: "percent" | "amount"
  currency?: string
  className?: string
}) {
  const dir = value > 0 ? "up" : value < 0 ? "down" : "flat"
  const Icon = dir === "up" ? ArrowUpRightIcon : dir === "down" ? ArrowDownRightIcon : MinusIcon
  return (
    <span
      data-direction={dir}
      className={cn(
        "inline-flex items-center gap-0.5 font-medium tabular-nums",
        dir === "up" && "text-success",
        dir === "down" && "text-destructive",
        dir === "flat" && "text-muted-foreground",
        className
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {dir === "up" ? "+" : dir === "down" ? "−" : ""}
      {fmt(value, kind, currency)}
    </span>
  )
}
