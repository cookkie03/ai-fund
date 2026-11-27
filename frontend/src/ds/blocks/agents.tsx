import * as React from "react"
import { ChevronRightIcon, CircleCheckIcon, CircleAlertIcon, Loader2Icon } from "lucide-react"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/ds/ui/card"
import { Button } from "@/ds/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/ds/ui/collapsible"
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/ds/ui/item"
import { Trace, TraceCollapsible, TraceCollapsibleContent, TraceCollapsibleTrigger, TraceDescription, TraceIcon, TraceLine, TraceTitle } from "@/ds/ui/trace"
import { CodeBlock, CodeBlockContent, CodeBlockCopyButton, CodeBlockHeader, CodeBlockTitle, CodeBlockActions } from "@/ds/ui/code-block"
import { AgentAvatar, resolveActor, type AgentStatus } from "@/ds/identity/agent-avatar"
import { Reveal } from "@/ds/motion"

export type AgentSeat = { actor: string; role: string; status?: AgentStatus; working?: string; lastLine?: string; lastActivity?: string; costToday?: string; tokensToday?: string }

/** One agent at a glance: who, what it is doing now, its last line and three meters. Fields the Runtime does not send are left out, never zero. */
export function AgentCard({ seat, index = 0, onAssign }: { seat: AgentSeat; index?: number; onAssign?: () => void }) {
  const a = resolveActor(seat.actor)
  const meters = ([["Last activity", seat.lastActivity], ["Cost today", seat.costToday], ["Tokens today", seat.tokensToday]] as const).filter(([, v]) => v)
  return (
    <Reveal index={index}>
      <Card className="group ds-lift relative h-full">
        <Button size="xs" variant="outline" className="absolute top-4 right-4 z-10 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100" onClick={onAssign}>Assign task</Button>
        <CardHeader>
          <CardTitle className="flex items-center gap-3"><AgentAvatar actor={seat.actor} size="lg" status={seat.status} /><span className="flex flex-col"><span>{a.name}</span><span className="text-xs font-normal text-muted-foreground">{seat.role}</span></span></CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {seat.working && <p><span className="text-muted-foreground">Now · </span>{seat.working}</p>}
          {seat.lastLine && <p className="line-clamp-2 text-muted-foreground">“{seat.lastLine}”</p>}
        </CardContent>
        {meters.length > 0 && (
          <CardFooter className="grid grid-cols-3 gap-2 text-xs">
            {meters.map(([k, v]) => <div key={k}><div className="text-muted-foreground">{k}</div><div className="font-medium tabular-nums">{v}</div></div>)}
          </CardFooter>
        )}
      </Card>
    </Reveal>
  )
}

export type AgentNode = { actor: string; role: string; status?: AgentStatus; note?: string; children?: AgentNode[] }

/** The agent hierarchy as an expandable tree: Portfolio Manager → instrument agents → the specialists they call. */
export function AgentTree({ root, defaultOpen = true }: { root: AgentNode; defaultOpen?: boolean }) {
  return <ItemGroup className="gap-1"><TreeNode node={root} depth={0} defaultOpen={defaultOpen} /></ItemGroup>
}
function TreeNode({ node, depth, defaultOpen }: { node: AgentNode; depth: number; defaultOpen: boolean }) {
  const [open, setOpen] = React.useState(defaultOpen && depth < 1)
  const row = (
    <Item size="sm" className="ds-reveal py-1.5" style={{ paddingLeft: 8 + depth * 20 }}>
      <ItemMedia>{node.children?.length ? <ChevronRightIcon className={"size-4 text-muted-foreground transition-transform duration-200 " + (open ? "rotate-90" : "")} /> : <span className="size-4" />}<AgentAvatar actor={node.actor} size="sm" status={node.status} /></ItemMedia>
      <ItemContent><ItemTitle>{resolveActor(node.actor).name}</ItemTitle><ItemDescription>{node.role}{node.note ? ` · ${node.note}` : ""}</ItemDescription></ItemContent>
      {node.children?.length ? <ItemActions><span className="text-xs text-muted-foreground tabular-nums">{node.children.length}</span></ItemActions> : null}
    </Item>
  )
  if (!node.children?.length) return row
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger render={<div role="button" className="cursor-pointer rounded-md hover:bg-muted" />}>{row}</CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col gap-1">{node.children.map((c) => <TreeNode key={c.actor} node={c} depth={depth + 1} defaultOpen={defaultOpen} />)}</CollapsibleContent>
    </Collapsible>
  )
}

export type ToolCall = { id: string; tool: string; summary: string; status: "ok" | "running" | "error"; duration?: string; time: string; input?: unknown; output?: unknown }

/** One tool call of an agent: status, tool name in mono, a one-line summary, duration; opens to Input and Output JSON with Copy. */
export function ToolCallRow({ call }: { call: ToolCall }) {
  const Icon = call.status === "running" ? Loader2Icon : call.status === "error" ? CircleAlertIcon : CircleCheckIcon
  return (
    <Trace>
      <TraceCollapsible>
        <TraceCollapsibleTrigger>
          <TraceLine status={call.status === "running" ? "running" : call.status === "error" ? "error" : undefined}>
            <TraceIcon><Icon className={call.status === "running" ? "animate-spin" : ""} /></TraceIcon>
            <TraceTitle><span className="font-mono text-xs text-foreground">{call.tool}</span> · {call.summary}</TraceTitle>
            <TraceDescription>{call.duration ? `${call.duration} · ` : ""}{call.time}</TraceDescription>
          </TraceLine>
        </TraceCollapsibleTrigger>
        <TraceCollapsibleContent className="flex flex-col gap-2 pt-2 pl-6">
          {(["input", "output"] as const).map((k) => call[k] !== undefined && (
            <CodeBlock key={k} size="sm">
              <CodeBlockHeader><CodeBlockTitle>{k === "input" ? "Input" : "Output"}</CodeBlockTitle><CodeBlockActions><CodeBlockCopyButton value={JSON.stringify(call[k], null, 2)} /></CodeBlockActions></CodeBlockHeader>
              <CodeBlockContent wrap>{JSON.stringify(call[k], null, 2)}</CodeBlockContent>
            </CodeBlock>
          ))}
        </TraceCollapsibleContent>
      </TraceCollapsible>
    </Trace>
  )
}

export type FeedEntry = { id: string; actor: string; text: string; time: string; meta?: React.ReactNode }

/** Recent activity as signed rows that arrive with a short stagger. */
export function ActivityFeed({ entries }: { entries: FeedEntry[] }) {
  return (
    <ItemGroup className="gap-1">
      {entries.map((e, i) => (
        <Item key={e.id} size="sm" className="ds-reveal" style={{ ["--ds-i" as string]: i }}>
          <ItemMedia><AgentAvatar actor={e.actor} size="sm" /></ItemMedia>
          <ItemContent><ItemTitle>{resolveActor(e.actor).name}</ItemTitle><ItemDescription>{e.text}</ItemDescription></ItemContent>
          <ItemActions className="flex-col items-end gap-1"><span className="text-xs text-muted-foreground tabular-nums">{e.time}</span>{e.meta}</ItemActions>
        </Item>
      ))}
    </ItemGroup>
  )
}
