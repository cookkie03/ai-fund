import { Avatar, AvatarBadge, AvatarFallback } from "@/ds/ui/avatar"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/ds/ui/tooltip"
import { cn } from "cn"

export type AgentStatus = "working" | "waiting" | "idle"

export type Actor = { id: string; name: string; initials: string; kind: "human" | "agent" | "system" }

const ROLES: Record<string, Omit<Actor, "id">> = {
  luca: { name: "Luca", initials: "LM", kind: "human" },
  portfolio_manager: { name: "Portfolio Manager", initials: "PM", kind: "agent" },
  risk_manager: { name: "Risk Manager", initials: "RM", kind: "agent" },
  technical_analyst: { name: "Technical Analyst", initials: "TA", kind: "agent" },
  market_analyst: { name: "Market Analyst", initials: "MA", kind: "agent" },
  sentiment_analyst: { name: "Sentiment Analyst", initials: "SA", kind: "agent" },
  fundamental_analyst: { name: "Fundamental Analyst", initials: "FA", kind: "agent" },
  system: { name: "System", initials: "SY", kind: "system" },
}

/** Resolve a Runtime actor id (`luca`, `portfolio_manager`, `ticker:NVDA`, `bond:IT0005…`) to a display identity. */
export function resolveActor(actor: string): Actor {
  const id = actor.trim().toLowerCase()
  const scoped = /^(ticker|bond|company|topic):(.+)$/i.exec(actor.trim())
  if (scoped) {
    const sym = scoped[2].toUpperCase()
    return { id, name: `${sym} agent`, initials: sym.slice(0, 2), kind: "agent" }
  }
  if (["cockpit", "cli", "telegram", "user"].includes(id)) return { id: "luca", ...ROLES.luca }
  const r = ROLES[id]
  if (r) return { id, ...r }
  const label = id.replace(/[-_]/g, " ") || "unknown"
  return { id, name: label.charAt(0).toUpperCase() + label.slice(1), initials: label.slice(0, 2).toUpperCase(), kind: "system" }
}

const STATUS_LABEL: Record<AgentStatus, string> = { working: "Working", waiting: "Waiting", idle: "Idle" }

/**
 * The one identity mark of the app: a contact-style circle with initials, in grays only.
 * Luca (human) is the solid dark circle, agents are muted circles; an optional status dot sits bottom-right.
 */
export function AgentAvatar({
  actor,
  size = "default",
  status,
  showName = false,
  description,
  className,
}: {
  actor: string
  size?: "sm" | "default" | "lg"
  status?: AgentStatus
  showName?: boolean
  description?: string
  className?: string
}) {
  const a = resolveActor(actor)
  const circle = (
    <Avatar size={size} aria-label={showName ? undefined : a.name}>
      <AvatarFallback
        className={cn(
          "font-medium",
          a.kind === "human" && "bg-primary text-primary-foreground",
          a.kind === "system" && "bg-background text-muted-foreground"
        )}
      >
        {a.initials}
      </AvatarFallback>
      {status && (
        <AvatarBadge
          aria-label={STATUS_LABEL[status]}
          className={cn(
            status === "working" && "bg-success ds-breathe",
            status === "waiting" && "bg-warning",
            status === "idle" && "bg-muted-foreground"
          )}
        />
      )}
    </Avatar>
  )
  const body = showName ? (
    <span className={cn("inline-flex min-w-0 items-center gap-2", className)}>
      {circle}
      <span className="flex min-w-0 flex-col leading-tight">
        <span className="truncate text-sm font-medium">{a.name}</span>
        {(description || status) && (
          <span className="truncate text-xs text-muted-foreground">{description ?? STATUS_LABEL[status!]}</span>
        )}
      </span>
    </span>
  ) : (
    <span className={cn("inline-flex", className)}>{circle}</span>
  )
  if (showName) return body
  return (
    <Tooltip>
      <TooltipTrigger render={body} />
      <TooltipContent>{a.name}{status ? ` · ${STATUS_LABEL[status]}` : ""}</TooltipContent>
    </Tooltip>
  )
}
