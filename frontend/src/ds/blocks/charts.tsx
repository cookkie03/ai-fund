import * as React from "react"
import { Area, AreaChart, CartesianGrid, Line, XAxis, YAxis } from "recharts"
import { createChart, CandlestickSeries, type IChartApi } from "lightweight-charts"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/ds/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/ds/ui/chart"
import { ToggleGroup, ToggleGroupItem } from "@/ds/ui/toggle-group"
import { Toggle } from "@/ds/ui/toggle"
import { AgentAvatar } from "@/ds/identity/agent-avatar"
import { PERIODS } from "@/ds/blocks/page"
import { cn } from "cn"

export type EquityPoint = { date: string; equity: number; benchmark?: number }

const config = { equity: { label: "Fund", color: "var(--chart-4)" }, benchmark: { label: "SPY", color: "var(--chart-2)" } } satisfies ChartConfig

/** Equity curve in grays (shadcn Chart / Recharts): the fund as an area, SPY as an optional thin line. */
export function EquityChart({ data, period = "1M", onPeriod, compare = false, onCompare, height = 240 }: { data: EquityPoint[]; period?: string; onPeriod?: (p: string) => void; compare?: boolean; onCompare?: (v: boolean) => void; height?: number }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Performance</CardTitle>
        <CardDescription>Equity over {period === "All" ? "all time" : period}</CardDescription>
        <CardAction className="flex items-center gap-2">
          <Toggle size="sm" variant="outline" pressed={compare} onPressedChange={onCompare}>SPY</Toggle>
          <ToggleGroup value={[period]} onValueChange={(v) => v[0] && onPeriod?.(v[0])} variant="outline" size="sm">{PERIODS.map((p) => <ToggleGroupItem key={p} value={p}>{p}</ToggleGroupItem>)}</ToggleGroup>
        </CardAction>
      </CardHeader>
      <CardContent>
        {data.length < 2 ? <p className="text-sm text-muted-foreground">Not enough history.</p> : (
          <ChartContainer config={config} className="w-full" style={{ height }}>
            <AreaChart data={data} margin={{ left: 0, right: 0, top: 4 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="date" tickLine={false} axisLine={false} tickMargin={8} minTickGap={32} />
              <YAxis hide domain={["auto", "auto"]} />
              <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="line" />} />
              <Area dataKey="equity" type="monotone" stroke="var(--color-equity)" strokeWidth={2} fill="var(--color-equity)" fillOpacity={0.12} animationDuration={700} />
              {compare && <Line dataKey="benchmark" type="monotone" stroke="var(--color-benchmark)" strokeWidth={1.5} strokeDasharray="4 4" dot={false} />}
            </AreaChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}

export type Candle = { time: string; open: number; high: number; low: number; close: number }

/** The TradingView chart (lightweight-charts), mounted with the library's own default styling. Never restyled: only size and data are passed. */
export function TradingViewChart({ data, height = 320, className }: { data: Candle[]; height?: number; className?: string }) {
  const ref = React.useRef<HTMLDivElement>(null)
  React.useEffect(() => {
    if (!ref.current) return
    const chart: IChartApi = createChart(ref.current, { autoSize: true })
    const s = chart.addSeries(CandlestickSeries)
    s.setData(data as never)
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [data])
  return <div ref={ref} className={cn("w-full overflow-hidden rounded-md", className)} style={{ height }} />
}

export type AuthorLayer = { actor: string; count: number }

/** Signatures over the chart: one avatar per author with drawings; click hides or shows that author's marks. Filters only what we draw, never the TradingView chart. */
export function AuthorFilter({ layers, hidden = [], onToggle }: { layers: AuthorLayer[]; hidden?: string[]; onToggle?: (actor: string) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-xs text-muted-foreground">Signatures</span>
      {layers.map((l) => {
        const off = hidden.includes(l.actor)
        return (
          <button key={l.actor} type="button" aria-pressed={!off} onClick={() => onToggle?.(l.actor)} className={cn("inline-flex items-center gap-1 rounded-full border py-0.5 pr-2 pl-0.5 text-xs transition-opacity hover:bg-muted", off && "opacity-40")}>
            <AgentAvatar actor={l.actor} size="sm" /><span className="tabular-nums">{l.count}</span>
          </button>
        )
      })}
    </div>
  )
}
