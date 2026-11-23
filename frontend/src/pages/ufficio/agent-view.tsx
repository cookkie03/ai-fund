import { ArrowUpRight, Check, ChevronDown, ChevronLeft, FileText, ListPlus, UsersRound, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { CollapsedRail } from "@/components/collapsed-rail";
import { Gutter } from "@/components/gutter";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { COCKPIT_TOPIC, topicTitle } from "@/features/office/api";
import { useChatTopics, useOfficeAgents, useToolCalls } from "@/features/office/hooks";
import type { ChatTopic } from "@/features/office/types";
import { AGENTS, author, tickerOf } from "@/lib/authors";
import { fmtWhen } from "@/lib/format";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { PANEL_LIMITS, PANEL_SHORTCUT, useShell } from "@/shell/shell-state";
import { AssignTask } from "./assign-task";
import { Conversation, TopicIcon } from "./conversation";
import { ROLE, StatusMark } from "./parts";
import { SideList, sortTopics } from "./side-list";
import { ToolStream } from "./tool-stream";
import { UsageButton } from "./usage";
import { useDossier } from "@/features/dossier/hooks";
import { DOSSIER_STATUS, fmtScore } from "@/features/dossier/labels";
import { DirectionTag } from "@/features/dossier/parts";
import { PendingProposals, usePendingProposals } from "./proposals";

/** The chat in view: the one in the URL, else the most recent, else Luca's thread with the agent. */
function useSelectedTopic(agent: string): { topic: string | null; topics: ChatTopic[] } {
  const [params] = useSearchParams();
  const q = useChatTopics(agent);
  const topics = q.data && q.data.source !== "unavailable" ? sortTopics(q.data.data) : [];
  const requested = params.get("chat");
  if (requested) return { topic: requested, topics };
  if (q.isPending) return { topic: null, topics };
  return { topic: topics[0]?.topic ?? COCKPIT_TOPIC, topics };
}

function ConversationHeader({ agent, topic, topics }: { agent: string; topic: string; topics: ChatTopic[] }) {
  const agents = useOfficeAgents();
  const a = agents.data && agents.data.source !== "unavailable" ? agents.data.data.find((x) => x.name === agent) : undefined;
  const t = topics.find((x) => x.topic === topic);
  const ticker = t?.ticker ?? null;
  return (
    <header className="flex h-11 shrink-0 items-center gap-2 pl-4 pr-2">
      <AuthorChip actor={agent} size="sm" />
      <h2 className="flex min-w-0 items-center gap-1.5 text-[13px] font-semibold text-fg">
        <span className="truncate">{author(agent).name}</span>
        <span className="text-fg-faint" aria-hidden>
          /
        </span>
        <TopicIcon topic={topic} className="text-fg-subtle" />
        <span className="truncate">{t?.title ?? topicTitle(topic)}</span>
      </h2>
      {a?.status && <StatusMark agent={agent} status={a.status} className="ml-1 hidden xl:inline-flex" />}
      <div className="ml-auto flex shrink-0 items-center gap-1">
        {ticker && !tickerOf(agent) && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Link to={`/ticker/${ticker}`} aria-label={`Apri la scheda di ${ticker}`} className="inline-flex h-7 items-center gap-1.5 rounded-control px-2 text-xs font-medium text-fg-muted outline-none transition-colors hover:bg-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-ring/60">
                <FileText className="size-3.5" strokeWidth={1.75} aria-hidden /> <span className="hidden xl:inline">Scheda</span>
              </Link>
            </TooltipTrigger>
            <TooltipContent>Scheda di {ticker}</TooltipContent>
          </Tooltip>
        )}
        {tickerOf(agent) && (
          <Link to={`/ticker/${tickerOf(agent)}`} className="inline-flex h-7 items-center gap-1.5 rounded-control bg-raised px-2.5 text-xs font-medium text-fg shadow-[inset_0_0.5px_0_oklch(1_0_0/0.08)] outline-none transition-colors hover:bg-selected focus-visible:ring-2 focus-visible:ring-ring/60">
            <FileText className="size-3.5" strokeWidth={1.75} aria-hidden /> Scheda {tickerOf(agent)}
          </Link>
        )}
        <UsageButton agent={agent} />
        <AssignTask agent={agent} ticker={ticker ?? a?.current?.ticker ?? null} />
      </div>
    </header>
  );
}

/**
 * Under a ticker agent's chat: what this conversation feeds. The dossier's version, state and thesis in one
 * line, and the way into it. The chat is where the work happens; the dossier is where it lands.
 */
function DossierStrip({ ticker }: { ticker: string }) {
  const q = useDossier(ticker);
  const d = q.data?.state === "ok" ? q.data.data : null;
  return (
    <Link
      to={`/ticker/${ticker}`}
      className="group mx-1.5 mb-1 flex min-h-9 shrink-0 items-center gap-2.5 rounded-control bg-[oklch(0_0_0/0.22)] px-3 py-1.5 text-xs outline-none transition-colors hover:bg-hover focus-visible:ring-2 focus-visible:ring-ring/60"
    >
      <FileText className="size-3.5 shrink-0 text-fg-subtle" strokeWidth={1.75} aria-hidden />
      {q.isPending ? (
        <span className="h-3 w-48 animate-pulse rounded-tag bg-hover" />
      ) : d ? (
        <span className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
          <span className="font-medium text-fg">Scheda di {ticker}</span>
          <span className="num text-fg-subtle">v{d.version}</span>
          <span className="text-fg-muted">{DOSSIER_STATUS[d.status] ?? d.status}</span>
          {d.thesis && (
            <span className="flex items-center gap-1.5">
              <DirectionTag value={d.thesis.direction} />
              <span className="num text-fg-muted">{fmtScore(d.thesis.conviction)}</span>
            </span>
          )}
          {d.stale_count > 0 && <span className="num text-warn">{d.stale_count === 1 ? "1 fatto vecchio" : `${d.stale_count} fatti vecchi`}</span>}
        </span>
      ) : q.data?.state === "unavailable" ? (
        <span className="min-w-0 truncate text-fg-muted">Scheda di {ticker}: in attesa di {q.data.endpoint}</span>
      ) : (
        <span className="min-w-0 truncate text-fg-muted">{ticker} non ha ancora una scheda</span>
      )}
      <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-fg-subtle group-hover:text-fg">
        Apri <ArrowUpRight className="size-3.5" aria-hidden />
      </span>
    </Link>
  );
}

/** The PM's queue as its own tile above the tool stream. */
function PmQueueTile({ className }: { className?: string }) {
  const { list } = usePendingProposals();
  return (
    <section aria-label="Proposte in attesa del PM" className={cn("flex min-h-0 flex-col overflow-hidden rounded-tile bg-ground", className)}>
      <h2 className="flex h-11 shrink-0 items-center gap-2 px-4 text-[13px] font-semibold tracking-[-0.005em] text-fg">
        In attesa del PM
        {list.length > 0 && <span className="num rounded-tag bg-warn-soft px-1.5 text-[10px] leading-4 text-warn">{list.length}</span>}
      </h2>
      <div className="min-h-0 flex-1 overflow-y-auto pb-1.5">
        <PendingProposals />
      </div>
    </section>
  );
}

function DesktopAgentView({ agent }: { agent: string }) {
  const { layout, setPanelOpen, setPanelSize } = useShell();
  const { topic, topics } = useSelectedTopic(agent);
  const { open, size } = layout;
  return (
    <div data-region="workspace" className="flex h-full min-h-0 min-w-0 flex-1 pb-2.5 pr-2.5">
      {open.left && (
        <>
          <SideList
            agent={agent}
            topic={topic ?? ""}
            onHide={() => setPanelOpen("left", false)}
            className="tile-enter-left shrink-0 overflow-hidden rounded-tile"
            style={{ width: size.left }}
          />
          <Gutter
            orientation="vertical"
            label="Larghezza di agenti e chat"
            value={size.left}
            min={PANEL_LIMITS.left.min}
            max={PANEL_LIMITS.left.max}
            direction={1}
            onResize={(px) => setPanelSize("left", px)}
            onReset={() => setPanelSize("left", PANEL_LIMITS.left.initial)}
          />
        </>
      )}
      {!open.left && <CollapsedRail side="left" label="Agenti e chat" icon={UsersRound} shortcut={PANEL_SHORTCUT.left} onOpen={() => setPanelOpen("left", true)} className="mr-2.5" />}
      {topic ? (
        <Conversation
          agent={agent}
          topic={topic}
          header={
            <>
              <ConversationHeader agent={agent} topic={topic} topics={topics} />
              {tickerOf(agent) && <DossierStrip ticker={tickerOf(agent)!} />}
            </>
          }
          className="min-w-[360px] flex-1 overflow-hidden rounded-tile"
        />
      ) : (
        <div className="flex-1 animate-pulse rounded-tile bg-ground" aria-busy aria-label="Caricamento della chat" />
      )}
      {open.right && (
        <>
          <Gutter
            orientation="vertical"
            label="Larghezza dello stream dei tool"
            value={size.right}
            min={PANEL_LIMITS.right.min}
            max={PANEL_LIMITS.right.max}
            direction={-1}
            onResize={(px) => setPanelSize("right", px)}
            onReset={() => setPanelSize("right", PANEL_LIMITS.right.initial)}
          />
          {agent === "portfolio_manager" ? (
            <div className="tile-enter-right flex shrink-0 flex-col gap-2.5" style={{ width: size.right }}>
              <PmQueueTile className="max-h-[48%] shrink-0" />
              <ToolStream agent={agent} onHide={() => setPanelOpen("right", false)} className="min-h-0 flex-1 overflow-hidden rounded-tile" />
            </div>
          ) : (
            <ToolStream agent={agent} onHide={() => setPanelOpen("right", false)} className="tile-enter-right shrink-0 overflow-hidden rounded-tile" style={{ width: size.right }} />
          )}
        </>
      )}
      {!open.right && <CollapsedRail side="right" label={agent === "portfolio_manager" ? "Coda e tool" : "Tool"} icon={Wrench} shortcut={PANEL_SHORTCUT.right} onOpen={() => setPanelOpen("right", true)} className="ml-2.5" />}
    </div>
  );
}

type MobileTab = "chat" | "tools" | "queue";

function MobileAgentView({ agent }: { agent: string }) {
  const navigate = useNavigate();
  const { topic, topics } = useSelectedTopic(agent);
  const agents = useOfficeAgents();
  const tools = useToolCalls(agent);
  const a = agents.data && agents.data.source !== "unavailable" ? agents.data.data.find((x) => x.name === agent) : undefined;
  const [tab, setTab] = useState<MobileTab>("chat");
  const { list: queue } = usePendingProposals();
  const ticker = tickerOf(agent);
  const current = topics.find((t) => t.topic === topic);
  const running = tools.data?.source === "runtime" ? tools.data.data.filter((c) => c.status === "running").length : 0;
  const options = topics.some((t) => t.topic === COCKPIT_TOPIC) ? topics : [...topics, { topic: COCKPIT_TOPIC, title: topicTitle(COCKPIT_TOPIC), last_message: null } as ChatTopic];

  useEffect(() => setTab("chat"), [agent]);

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center gap-2 px-2 pb-2 pt-1">
        <Link to="/ufficio" aria-label="Torna all'ufficio" className="grid size-9 shrink-0 place-items-center rounded-control text-fg-subtle transition-colors hover:bg-hover hover:text-fg">
          <ChevronLeft className="size-5" />
        </Link>
        <AuthorChip actor={agent} size="md" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-semibold text-fg">{author(agent).name}</p>
          {a?.status ? <StatusMark agent={agent} status={a.status} className="text-2xs" /> : <p className="truncate text-2xs text-fg-subtle">{a?.role ?? ROLE[agent] ?? "Agente"}</p>}
        </div>
        {ticker && (
          <Link to={`/ticker/${ticker}`} aria-label={`Apri la scheda di ${ticker}`} className="grid size-9 shrink-0 place-items-center rounded-control bg-raised text-fg transition-colors hover:bg-selected">
            <FileText className="size-4" strokeWidth={1.75} />
          </Link>
        )}
        <AssignTask
          agent={agent}
          ticker={current?.ticker ?? a?.current?.ticker ?? null}
          trigger={
            <Button variant="ghost" size="icon" aria-label="Assegna task">
              <ListPlus className="size-4" />
            </Button>
          }
        />
      </div>

      <div className="flex shrink-0 gap-2 px-2 pb-2">
        <DropdownMenu>
          <DropdownMenuTrigger className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-control bg-ground px-3 text-left text-[13px] font-medium text-fg">
            {topic && <TopicIcon topic={topic} className="text-fg-subtle" />}
            <span className="min-w-0 truncate">{topic ? (current?.title ?? topicTitle(topic)) : "Caricamento…"}</span>
            <span className="num ml-auto text-2xs font-normal text-fg-subtle">{topics.length > 1 ? `${topics.length} chat` : ""}</span>
            <ChevronDown className="size-4 shrink-0 text-fg-subtle" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-[min(340px,calc(100vw-16px))]">
            <DropdownMenuLabel className="text-2xs font-normal text-fg-subtle">Chat di {author(agent).short}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {options.map((t) => (
              <DropdownMenuItem key={t.topic} onSelect={() => navigate(`/ufficio/${agent}?chat=${encodeURIComponent(t.topic)}`, { replace: true })} className="items-start gap-2 py-2">
                <TopicIcon topic={t.topic} className="mt-0.5 text-fg-subtle" />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-[13px] font-medium text-fg">{t.title}</span>
                    <span className="num ml-auto text-2xs text-fg-subtle">{t.last_message ? fmtWhen(t.last_message.ts) : ""}</span>
                  </span>
                  <span className="block truncate text-xs text-fg-subtle">{t.last_message?.text ?? "Nessun messaggio"}</span>
                </span>
                <Check className={cn("mt-0.5 size-4", t.topic === topic ? "opacity-100" : "opacity-0")} />
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div role="tablist" aria-label="Sezioni dell'agente" className="mx-2 mb-2 flex h-9 shrink-0 gap-0.5 rounded-control bg-ground p-0.5">
        {(agent === "portfolio_manager" ? (["chat", "tools", "queue"] as const) : (["chat", "tools"] as const)).map((id) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn("flex flex-1 items-center justify-center gap-1.5 rounded-item text-xs font-medium transition-colors duration-150", tab === id ? "bg-hover text-fg" : "text-fg-subtle hover:text-fg")}
          >
            {id === "chat" ? "Chat" : id === "tools" ? "Tool" : "Proposte"}
            {id === "tools" && running > 0 && <span className="num rounded-tag bg-hover px-1 text-[10px] leading-4 text-fg-muted">{running} in corso</span>}
            {id === "queue" && queue.length > 0 && <span className="num rounded-tag bg-warn-soft px-1 text-[10px] leading-4 text-warn">{queue.length}</span>}
          </button>
        ))}
      </div>

      <div className="mx-2 mb-2 flex min-h-0 flex-1 flex-col overflow-hidden rounded-tile bg-ground">
        {tab === "chat" ? (
          topic ? (
            <Conversation agent={agent} topic={topic} className="flex-1" header={ticker ? <div className="pt-1.5"><DossierStrip ticker={ticker} /></div> : undefined} />
          ) : (
            <div className="flex-1 animate-pulse" aria-busy />
          )
        ) : tab === "tools" ? (
          <ToolStream agent={agent} className="flex-1" />
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto py-1.5">
            <PendingProposals />
          </div>
        )}
      </div>
    </div>
  );
}

export function AgentView({ agent }: { agent: string }) {
  const desktop = useMediaQuery("(min-width: 1024px)");
  useEffect(() => {
    document.title = `${author(agent).name} · Ufficio`;
  }, [agent]);
  if (!AGENTS[agent] && !/^[a-z_]+$/.test(agent) && !tickerOf(agent)) return null;
  return desktop ? <DesktopAgentView agent={agent} /> : <MobileAgentView agent={agent} />;
}

