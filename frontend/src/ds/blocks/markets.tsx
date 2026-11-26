import * as React from "react"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/ds/ui/card"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/ds/ui/resizable"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/ds/ui/tabs"
import { ScrollArea } from "@/ds/ui/scroll-area"
import { AgentAvatar } from "@/ds/identity/agent-avatar"
import { Delta } from "@/ds/identity/delta"
import { PriceFlash } from "@/ds/motion"
import { AuthorFilter, TradingViewChart, type AuthorLayer, type Candle } from "@/ds/blocks/charts"
import { cn } from "cn"

export type WatchItem = { symbol: string; name: string; price: number; changePct: number; signer?: string }

/** The watchlist: symbol and name, price that flashes, change, and who put it there. */
export function Watchlist({ items, active, onSelect }: { items: WatchItem[]; active?: string; onSelect?: (s: string) => void }) {
  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-0.5 p-1.5">
        {items.map((it, i) => (
          <button key={it.symbol} type="button" onClick={() => onSelect?.(it.symbol)} className={cn("ds-reveal flex items-center gap-2 rounded-md px-2 py-2 text-left transition-colors hover:bg-muted", active === it.symbol && "bg-muted")} style={{ ["--ds-i" as string]: i }}>
            {it.signer ? <AgentAvatar actor={it.signer} size="sm" /> : <span className="size-6 shrink-0" aria-hidden />}
            <span className="min-w-0 flex-1"><span className="block text-sm font-medium">{it.symbol}</span><span className="block truncate text-xs text-muted-foreground">{it.name}</span></span>
            <span className="flex flex-col items-end text-sm"><PriceFlash value={it.price}>{`$${it.price.toFixed(2)}`}</PriceFlash><Delta value={it.changePct} className="text-xs" /></span>
          </button>
        ))}
      </div>
    </ScrollArea>
  )
}

/** Markets workspace: resizable panels (watchlist | chart | activity) over a resizable bottom panel for orders. */
export function MarketsWorkspace({ watch, candles, layers, symbol, activity, orders, height = 640 }: { watch: WatchItem[]; candles: Candle[]; layers: AuthorLayer[]; symbol: string; activity?: React.ReactNode; orders?: React.ReactNode; height?: number }) {
  const [hidden, setHidden] = React.useState<string[]>([])
  const toggle = (a: string) => setHidden((h) => (h.includes(a) ? h.filter((x) => x !== a) : [...h, a]))
  return (
    <div style={{ height }}>
      <ResizablePanelGroup orientation="vertical">
        <ResizablePanel defaultSize="72%" minSize="40%">
          <ResizablePanelGroup orientation="horizontal">
            <ResizablePanel defaultSize="22%" minSize="15%" className="pr-1.5"><Card size="sm" className="h-full gap-0 py-0"><CardHeader className="py-3"><CardTitle>Watchlist</CardTitle></CardHeader><Watchlist items={watch} active={symbol} /></Card></ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize="53%" minSize="30%" className="px-1.5">
              <Card size="sm" className="h-full">
                <CardHeader><CardTitle>{symbol}</CardTitle><CardAction><AuthorFilter layers={layers} hidden={hidden} onToggle={toggle} /></CardAction></CardHeader>
                <CardContent className="min-h-0 flex-1"><TradingViewChart data={candles} height={300} /></CardContent>
              </Card>
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize="25%" minSize="15%" className="pl-1.5">
              <Card size="sm" className="h-full">
                <Tabs defaultValue="agents" className="px-4"><TabsList><TabsTrigger value="agents">Agents</TabsTrigger><TabsTrigger value="drawings">Drawings</TabsTrigger></TabsList>
                  <TabsContent value="agents" className="pt-2">{activity}</TabsContent>
                  <TabsContent value="drawings" className="pt-2 text-sm text-muted-foreground">Drawings by author.</TabsContent>
                </Tabs>
              </Card>
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel defaultSize="28%" minSize="12%" className="pt-3"><Card size="sm" className="h-full overflow-auto"><CardHeader><CardTitle>Orders</CardTitle></CardHeader><CardContent>{orders}</CardContent></Card></ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}
