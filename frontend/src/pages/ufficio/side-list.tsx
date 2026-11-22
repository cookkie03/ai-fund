import { ChevronLeft, PanelLeftClose } from "lucide-react";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { IconButton } from "@/components/tile";
import { useChatTopics, useOfficeAgents } from "@/features/office/hooks";
import type { ChatTopic, OfficeAgent } from "@/features/office/types";
import { AGENTS, AGENT_IDS, author } from "@/lib/authors";
import { fmtWhen } from "@/lib/format";
import { useNow } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { PANEL_SHORTCUT } from "@/shell/shell-state";
import { TopicIcon } from "./conversation";
import { SourceNote, StatusMark } from "./parts";

/** Agents first, then the chosen agent's chats, like Slack's sidebar. */
export function sortTopics(topics: ChatTopic[]): ChatTopic[] {
  return [...topics].sort((a, b) => (Date.parse(b.last_message?.ts ?? "") || 0) - (Date.parse(a.last_message?.ts ?? "") || 0));
}

export function agentList(agents: OfficeAgent[] | undefined): string[] {
  const names = agents?.map((a) => a.name) ?? [];
  return names.length ? names : AGENT_IDS;
}

export function TopicRow({ t, selected, to, now }: { t: ChatTopic; selected: boolean; to: string; now: number }) {
  const last = t.last_message;
  const who = last ? author(last.author) : null;
  return (
    <Link
      to={to}
      aria-current={selected ? "page" : undefined}
      className={cn(
        "group block rounded-item px-2.5 py-2 outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring/60",
        selected ? "bg-selected shadow-[inset_0_0.5px_0_oklch(1_0_0/0.06)]" : "hover:bg-hover",
      )}
    >
      <span className="flex min-w-0 items-center gap-1.5">
        <TopicIcon topic={t.topic} className={selected ? "text-fg-muted" : "text-fg-subtle"} />
        <span className={cn("min-w-0 truncate text-[13px]", selected ? "font-semibold text-fg" : "font-medium text-fg")}>{t.title}</span>
        {t.message_count > 0 && <span className="num shrink-0 rounded-tag bg-hover px-1 text-[10px] leading-4 text-fg-subtle">{t.message_count}</span>}
        <span className="num ml-auto shrink-0 text-2xs text-fg-subtle">{last ? fmtWhen(last.ts, now) : ""}</span>
      </span>
      <span className="mt-0.5 block truncate pl-5 text-xs text-fg-subtle">
        {last ? (
          <>
            <span className="text-fg-muted">{who?.kind === "human" ? "Tu" : who?.short}:</span> {last.text}
          </>
        ) : (
          "Nessun messaggio"
        )}
      </span>
    </Link>
  );
}

export function SideList({ agent, topic, onHide, className, style }: { agent: string; topic: string; onHide?: () => void; className?: string; style?: CSSProperties }) {
  const agentsQ = useOfficeAgents();
  const topicsQ = useChatTopics(agent);
  const now = useNow(30_000);
  const agents = agentsQ.data && agentsQ.data.source !== "unavailable" ? agentsQ.data.data : undefined;
  const names = agentList(agents);
  const topics = topicsQ.data && topicsQ.data.source !== "unavailable" ? sortTopics(topicsQ.data.data) : [];

  return (
    <nav aria-label="Agenti e chat" className={cn("flex min-h-0 flex-col bg-ground", className)} style={style}>
      <header className="flex h-11 shrink-0 items-center gap-1 pl-2 pr-2">
        <Link to="/ufficio" className="inline-flex h-7 items-center gap-1 rounded-control pl-1 pr-2 text-[13px] font-semibold text-fg transition-colors hover:bg-hover">
          <ChevronLeft className="size-4 text-fg-subtle" aria-hidden /> Ufficio
        </Link>
        {onHide && (
          <span className="ml-auto">
            <IconButton icon={PanelLeftClose} label="Nascondi agenti e chat" shortcut={PANEL_SHORTCUT.left} onClick={onHide} />
          </span>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        <h3 className="px-2.5 pb-1 pt-1 text-2xs font-medium text-fg-subtle">Agenti</h3>
        <ul>
          {names.map((name) => {
            const a = agents?.find((x) => x.name === name);
            const active = name === agent;
            return (
              <li key={name}>
                <Link
                  to={`/ufficio/${name}`}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex h-8 items-center gap-2 rounded-item px-2.5 text-[13px] outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring/60",
                    active ? "bg-selected font-semibold text-fg shadow-[inset_0_0.5px_0_oklch(1_0_0/0.06)]" : "text-fg-muted hover:bg-hover hover:text-fg",
                  )}
                >
                  <AuthorChip actor={name} size="xs" tooltip={AGENTS[name]?.name} />
                  <span className="min-w-0 truncate">{author(name).name}</span>
                  {a?.current?.ticker && <span className="num ml-auto text-2xs font-normal text-fg-subtle">{a.current.ticker}</span>}
                  {a?.status && <StatusMark agent={name} status={a.status} compact className={a.current?.ticker ? "" : "ml-auto"} />}
                </Link>
              </li>
            );
          })}
        </ul>

        <h3 className="mt-4 flex items-center gap-1.5 px-2.5 pb-1 text-2xs font-medium text-fg-subtle">
          Chat di {AGENTS[agent]?.short ?? agent}
          {topics.length > 0 && <span className="num font-normal">{topics.length}</span>}
        </h3>
        {topicsQ.isPending ? (
          <div className="space-y-1 px-1" aria-busy aria-label="Caricamento delle chat">
            {[0, 1, 2].map((i) => (
              <div key={i} className="space-y-1.5 px-1.5 py-2">
                <span className="block h-3 w-1/2 animate-pulse rounded-tag bg-hover" />
                <span className="block h-2.5 w-4/5 animate-pulse rounded-tag bg-hover" />
              </div>
            ))}
          </div>
        ) : topicsQ.isError ? (
          <p className="px-2.5 py-2 text-xs text-down">Chat non disponibili: {topicsQ.error.message}</p>
        ) : topics.length === 0 ? (
          <p className="px-2.5 py-2 text-xs leading-relaxed text-fg-subtle">{AGENTS[agent]?.short ?? agent} non ha ancora chat. Scrivigli per aprirne una.</p>
        ) : (
          <ul className="space-y-px">
            {topics.map((t) => (
              <li key={t.topic}>
                <TopicRow t={t} selected={t.topic === topic} to={`/ufficio/${agent}?chat=${encodeURIComponent(t.topic)}`} now={now} />
              </li>
            ))}
          </ul>
        )}
        <SourceNote sourced={topicsQ.data} className="px-2.5 pt-3" />
      </div>
    </nav>
  );
}
