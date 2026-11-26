import { MoreHorizontalIcon } from "lucide-react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/ds/ui/table"
import { Button } from "@/ds/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/ds/ui/dropdown-menu"
import { AgentAvatar } from "@/ds/identity/agent-avatar"
import { Delta } from "@/ds/identity/delta"
import { PriceFlash } from "@/ds/motion"
import { StatusBadge, type OrderState } from "@/ds/identity/status-badge"
import { cn } from "cn"

export type Position = { symbol: string; name: string; qty: string; price: number; value: string; pnl: number; pnlPct: number; weight: string; currency?: string }

const px = (v: number, c = "$") => `${c}${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

/** Open positions, compact rows (32 px). Prices flash on change; actions per row in a menu. */
export function PositionsTable({ rows, onSelect, halted }: { rows: Position[]; onSelect?: (s: string) => void; halted?: boolean }) {
  return (
    <Table className="[&_td]:py-1.5">
      <TableHeader>
        <TableRow>
          <TableHead>Instrument</TableHead><TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Price</TableHead>
          <TableHead className="text-right">Value</TableHead><TableHead className="text-right">P&amp;L</TableHead><TableHead className="text-right">Weight</TableHead><TableHead className="w-8" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r, i) => (
          <TableRow key={r.symbol} className="ds-reveal cursor-pointer" style={{ ["--ds-i" as string]: i }} onClick={() => onSelect?.(r.symbol)}>
            <TableCell><div className="font-medium">{r.symbol}</div><div className="text-xs text-muted-foreground">{r.name}</div></TableCell>
            <TableCell className="text-right tabular-nums">{r.qty}</TableCell>
            <TableCell className="text-right"><PriceFlash value={r.price}>{px(r.price, r.currency)}</PriceFlash></TableCell>
            <TableCell className="text-right tabular-nums">{r.value}</TableCell>
            <TableCell className="text-right"><div className="flex flex-col items-end"><Delta value={r.pnl} kind="amount" /><Delta value={r.pnlPct} className="text-xs" /></div></TableCell>
            <TableCell className="text-right tabular-nums">{r.weight}</TableCell>
            <TableCell onClick={(e) => e.stopPropagation()}>
              <DropdownMenu>
                <DropdownMenuTrigger render={<Button variant="ghost" size="icon-xs" aria-label={`Actions for ${r.symbol}`} />}><MoreHorizontalIcon /></DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuGroup><DropdownMenuLabel>{r.symbol}</DropdownMenuLabel></DropdownMenuGroup>
                  <DropdownMenuItem disabled={halted}>Edit stop &amp; target</DropdownMenuItem>
                  <DropdownMenuItem disabled={halted}>Reduce position</DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" disabled={halted}>Close position</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export type Order = { id: string; time: string; agent: string; symbol: string; side: "Buy" | "Sell"; qty: string; price: string; state: OrderState }

/** Orders with their author, side and state. Side reads as a word; colour only on the state badge. */
export function OrdersTable({ rows }: { rows: Order[] }) {
  return (
    <Table className="[&_td]:py-1.5">
      <TableHeader>
        <TableRow><TableHead>Time</TableHead><TableHead>By</TableHead><TableHead>Instrument</TableHead><TableHead>Side</TableHead><TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Price</TableHead><TableHead>Status</TableHead></TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r, i) => (
          <TableRow key={r.id} className="ds-reveal" style={{ ["--ds-i" as string]: i }}>
            <TableCell className="text-muted-foreground tabular-nums">{r.time}</TableCell>
            <TableCell><AgentAvatar actor={r.agent} size="sm" /></TableCell>
            <TableCell className="font-medium">{r.symbol}</TableCell>
            <TableCell className={cn(r.side === "Buy" ? "text-success" : "text-destructive")}>{r.side}</TableCell>
            <TableCell className="text-right tabular-nums">{r.qty}</TableCell>
            <TableCell className="text-right tabular-nums">{r.price}</TableCell>
            <TableCell><StatusBadge state={r.state} /></TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
