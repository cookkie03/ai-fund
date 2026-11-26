import * as React from "react"
import { CheckIcon, TriangleAlertIcon, OctagonAlertIcon } from "lucide-react"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/ds/ui/card"
import { ToggleGroup, ToggleGroupItem } from "@/ds/ui/toggle-group"
import { cn } from "cn"

export type LimitState = "within" | "near" | "over"

/** State of a value against its limit. For a maximum, near starts at 80%; for a minimum (cash reserve, R:R), near starts below 1.25× the floor. */
export function limitState(value: number, limit: number, kind: "max" | "min" = "max"): LimitState {
  if (kind === "max") return value > limit ? "over" : value >= limit * 0.8 ? "near" : "within"
  return value < limit ? "over" : value < limit * 1.25 ? "near" : "within"
}

const WORD: Record<LimitState, { label: string; icon: typeof CheckIcon; cls: string }> = {
  within: { label: "Within limit", icon: CheckIcon, cls: "text-muted-foreground" },
  near: { label: "Near limit", icon: TriangleAlertIcon, cls: "text-warning" },
  over: { label: "Over limit", icon: OctagonAlertIcon, cls: "text-destructive" },
}

/** A value drawn against its limit: gray fill, amber when near, red when over, a tick where the risk gate draws the line, and always the word. */
export function LimitBar({ label, value, limit, scale = 100, kind = "max", format = (v: number) => `${v.toFixed(1)}%`, detail }: { label: string; value: number; limit: number; scale?: number; kind?: "max" | "min"; format?: (v: number) => string; detail?: string }) {
  const s = limitState(value, limit, kind)
  const W = WORD[s]
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums">{format(value)} <span className="text-muted-foreground">/ {kind === "max" ? "max" : "min"} {format(limit)}</span></span>
      </div>
      <div className="relative h-2 rounded-full bg-muted" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={scale} aria-label={label}>
        <div className={cn("ds-grow-x absolute inset-y-0 left-0 rounded-full", s === "within" && "bg-chart-3", s === "near" && "bg-warning", s === "over" && "bg-destructive")} style={{ width: `${Math.min(100, (value / scale) * 100)}%` }} />
        <div className="absolute -inset-y-1 w-0.5 rounded-full bg-foreground" style={{ left: `${Math.min(100, (limit / scale) * 100)}%` }} aria-hidden />
      </div>
      <div className={cn("flex items-center gap-1 text-xs", W.cls)}><W.icon className="size-3.5" />{W.label}{detail && <span className="text-muted-foreground"> · {detail}</span>}</div>
    </div>
  )
}

export type AllocationRow = { name: string; weight: number; limit: number }

/** Allocation as rows of limit bars (no pie), by sector or by position, closed by cash against its reserve. */
export function AllocationList({ bySector, byPosition, cash, cashFloor }: { bySector: AllocationRow[]; byPosition: AllocationRow[]; cash: number; cashFloor: number }) {
  const [mode, setMode] = React.useState<"sector" | "position">("sector")
  const rows = mode === "sector" ? bySector : byPosition
  const flagged = rows.filter((r) => limitState(r.weight, r.limit) !== "within")
  return (
    <Card>
      <CardHeader>
        <CardTitle>Allocation</CardTitle>
        <CardDescription>{flagged.length ? `${flagged.length} near or over its limit` : "Everything within limits"}</CardDescription>
        <CardAction>
          <ToggleGroup value={[mode]} onValueChange={(v) => v[0] && setMode(v[0] as "sector" | "position")} variant="outline" size="sm">
            <ToggleGroupItem value="sector">Sector</ToggleGroupItem><ToggleGroupItem value="position">Position</ToggleGroupItem>
          </ToggleGroup>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {rows.map((r) => <LimitBar key={r.name} label={r.name} value={r.weight} limit={r.limit} scale={Math.max(40, r.limit * 1.3)} />)}
        <LimitBar label="Cash" value={cash} limit={cashFloor} kind="min" scale={40} detail="reserve floor" />
      </CardContent>
    </Card>
  )
}
