import * as React from "react"
import { cn } from "cn"

/** Fades and lifts its child in on mount; `index` staggers siblings by 60 ms. */
export function Reveal({ index = 0, className, children, ...props }: React.ComponentProps<"div"> & { index?: number }) {
  return (
    <div className={cn("ds-reveal", className)} style={{ ["--ds-i" as string]: index, ...props.style }} {...props}>
      {children}
    </div>
  )
}

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches

/** Counts up to `value` (600 ms, ease-out) and re-tweens on change. Always tabular. */
export function AnimatedNumber({
  value,
  format = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  duration = 600,
  className,
}: {
  value: number
  format?: (v: number) => string
  duration?: number
  className?: string
}) {
  const [shown, setShown] = React.useState(reduced() ? value : 0)
  const from = React.useRef(shown)
  React.useEffect(() => {
    if (reduced()) { setShown(value); return }
    const start = performance.now(), a = from.current, b = value
    let raf = 0
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration), e = 1 - Math.pow(1 - p, 4)
      const v = a + (b - a) * e
      setShown(v); from.current = v
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])
  return <span className={cn("tabular-nums", className)}>{format(shown)}</span>
}

/** Flashes its background once in success/destructive when `value` rises/falls. The flash carries information, so it stays under reduced motion. */
export function PriceFlash({ value, children, className }: { value: number; children: React.ReactNode; className?: string }) {
  const prev = React.useRef(value)
  const [dir, setDir] = React.useState<"up" | "down" | null>(null)
  const [k, setK] = React.useState(0)
  React.useEffect(() => {
    if (value !== prev.current) { setDir(value > prev.current ? "up" : "down"); setK((x) => x + 1); prev.current = value }
  }, [value])
  return (
    <span key={k} className={cn("rounded-sm px-1 tabular-nums", dir === "up" && "ds-flash-up", dir === "down" && "ds-flash-down", className)}>
      {children}
    </span>
  )
}
