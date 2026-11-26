import * as React from "react"
import { CalendarIcon } from "lucide-react"
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/ds/ui/card"
import { Button } from "@/ds/ui/button"
import { Badge } from "@/ds/ui/badge"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/ds/ui/dialog"
import { ToggleGroup, ToggleGroupItem } from "@/ds/ui/toggle-group"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/ds/ui/field"
import { Input } from "@/ds/ui/input"
import { Textarea } from "@/ds/ui/textarea"
import { Popover, PopoverContent, PopoverTrigger } from "@/ds/ui/popover"
import { Calendar } from "@/ds/ui/calendar"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/ds/ui/tooltip"
import { AgentAvatar } from "@/ds/identity/agent-avatar"
import { Reveal } from "@/ds/motion"
import { cn } from "cn"

export type Proposal = { id: string; agent: string; instrument: string; name?: string; side: "Long" | "Short" | "Sell"; conviction: number; size: string; rr: number; waiting: string; entry?: string; stop?: string; target?: string }

/** One agent proposal to decide, like a payment request in a banking app. Approve is the only primary. */
export function ProposalCard({ p, index = 0, halted, onApprove, onDecide }: { p: Proposal; index?: number; halted?: boolean; onApprove?: () => void; onDecide?: () => void }) {
  const lowRR = p.rr < 1.5
  const approve = <Button size="sm" disabled={halted} onClick={onApprove}>Approve</Button>
  return (
    <Reveal index={index}>
      <Card className="ds-lift">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">{p.instrument}<Badge variant="outline">{p.side}</Badge></CardTitle>
          <CardDescription>{p.name ?? "Proposal"} · waiting {p.waiting}</CardDescription>
          <CardAction><AgentAvatar actor={p.agent} /></CardAction>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-3 gap-3 text-sm">
            <div><dt className="text-xs text-muted-foreground">Conviction</dt><dd className="font-medium tabular-nums">{p.conviction.toFixed(2)}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Size</dt><dd className="font-medium tabular-nums">{p.size}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Risk : reward</dt><dd className={cn("font-medium tabular-nums", lowRR && "text-warning")}>{p.rr.toFixed(1)}{lowRR && " · low"}</dd></div>
          </dl>
          {p.entry && <p className="mt-3 text-xs text-muted-foreground tabular-nums">Entry {p.entry} · stop {p.stop} · target {p.target}</p>}
        </CardContent>
        <CardFooter className="gap-2">
          {halted ? <Tooltip><TooltipTrigger render={<span />}>{approve}</TooltipTrigger><TooltipContent>Trading halted</TooltipContent></Tooltip> : approve}
          <Button size="sm" variant="outline" onClick={onDecide}>Decide</Button>
        </CardFooter>
      </Card>
    </Reveal>
  )
}

const ACTIONS = { accept: "Accept", postpone: "Postpone", reject: "Reject", ask: "Ask" } as const
type Action = keyof typeof ACTIONS

/** "Decide for the PM": pick an action, fill what it needs, give a reason; the primary is named after the action. */
export function DecideDialog({ p, open, onOpenChange, halted, refusal, onSubmit }: { p: Proposal; open?: boolean; onOpenChange?: (o: boolean) => void; halted?: boolean; refusal?: string; onSubmit?: (a: { action: Action; reason: string; size?: string; until?: Date }) => void }) {
  const [action, setAction] = React.useState<Action>("accept")
  const [reason, setReason] = React.useState("")
  const [until, setUntil] = React.useState<Date | undefined>()
  const [size, setSize] = React.useState(p.size)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Decide for the Portfolio Manager</DialogTitle>
          <DialogDescription className="flex items-center gap-2"><AgentAvatar actor={p.agent} size="sm" />{p.instrument} · {p.side} · conviction {p.conviction.toFixed(2)} · R:R {p.rr.toFixed(1)}</DialogDescription>
        </DialogHeader>
        <FieldGroup>
          <ToggleGroup value={[action]} onValueChange={(v) => v[0] && setAction(v[0] as Action)} variant="outline" className="w-full">
            {(Object.keys(ACTIONS) as Action[]).map((a) => <ToggleGroupItem key={a} value={a} className="flex-1" disabled={a === "accept" && halted}>{ACTIONS[a]}</ToggleGroupItem>)}
          </ToggleGroup>
          {action === "accept" && <Field><FieldLabel>Size</FieldLabel><Input value={size} onChange={(e) => setSize(e.target.value)} /><FieldDescription>Change it to resize the proposal before it goes to the risk gate.</FieldDescription></Field>}
          {action === "postpone" && (
            <Field>
              <FieldLabel>Until</FieldLabel>
              <Popover>
                <PopoverTrigger render={<Button variant="outline" className="justify-start font-normal" />}><CalendarIcon />{until ? until.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "Pick a date"}</PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start"><Calendar mode="single" selected={until} onSelect={setUntil} /></PopoverContent>
              </Popover>
            </Field>
          )}
          <Field><FieldLabel>Reason</FieldLabel><Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Required — the agents read it." /></Field>
          {refusal && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{refusal}</p>}
        </FieldGroup>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange?.(false)}>Cancel</Button>
          <Button variant={action === "reject" ? "destructive" : "default"} disabled={!reason.trim()} onClick={() => onSubmit?.({ action, reason, size, until })}>{ACTIONS[action]}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
