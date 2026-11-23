import { Loader2, RotateCw, TriangleAlert, Wrench, X } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, type ReactNode } from "react";
import { AuthorChip } from "@/components/author-chip";
import { author } from "@/lib/authors";
import { parseTs } from "@/lib/format";
import { useNow } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { ActionCard } from "./action-card";
import { useConversation, useRuntimeDown } from "./hooks";
import { RefTag } from "./refs";
import { useBridge, type PendingSend } from "./state";
import type { BridgeMessage, Conversation, LiveTurn } from "./types";

const dayFmt = new Intl.DateTimeFormat("it-IT", { weekday: "long", day: "numeric", month: "long" });
const timeFmt = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" });

function dayLabel(ms: number, now: number): string {
  const d = new Date(ms);
  if (d.toDateString() === new Date(now).toDateString()) return "Oggi";
  const y = new Date(now);
  y.setDate(y.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return "Ieri";
  return dayFmt.format(d);
}

type Item = { kind: "message"; m: BridgeMessage } | { kind: "pending"; p: PendingSend };
type Group = { day: string; author: string; relay: boolean; firstTs: string; items: Item[] };

/** Same author within 5 minutes shares one header; errors, relays and actions always open their own group. */
function group(items: Item[], now: number): Group[] {
  const out: Group[] = [];
  for (const it of items) {
    const authorId = it.kind === "message" ? it.m.author : "luca";
    const ts = it.kind === "message" ? it.m.ts : new Date(now).toISOString();
    const relay = it.kind === "message" && it.m.kind === "agent_relay";
    const solo = it.kind === "message" && (it.m.kind === "error" || it.m.kind === "action");
    const ms = parseTs(ts) ?? now;
    const day = dayLabel(ms, now);
    const last = out.at(-1);
    const lastItem = last?.items.at(-1);
    const lastMs = lastItem ? (lastItem.kind === "message" ? parseTs(lastItem.m.ts) ?? 0 : now) : 0;
    const lastSolo = lastItem?.kind === "message" && (lastItem.m.kind === "error" || lastItem.m.kind === "action");
    if (last && !solo && !lastSolo && last.author === authorId && last.relay === relay && last.day === day && ms - lastMs < 5 * 60_000) last.items.push(it);
    else out.push({ day, author: authorId, relay, firstTs: ts, items: [it] });
  }
  return out;
}

/** The running turn of a conversation: the live `bridge.status` event wins over the read's `status`. */
export function turnOf(id: number | null, live: Record<number, LiveTurn>, readStatus: "idle" | "thinking" | undefined): LiveTurn | null {
  if (id === null) return null;
  const l = live[id];
  if (l) return l.status === "idle" ? null : l;
  return readStatus === "thinking" ? { status: "thinking", tool: null, at: 0 } : null;
}

function MessageBody({ m, compact }: { m: BridgeMessage; compact: boolean }) {
  const { contextLabel } = useBridge();
  if (m.kind === "error") {
    return (
      <div role="note" className="mt-1 flex max-w-[60ch] gap-2 rounded-item bg-warn-soft px-2.5 py-2 text-sm leading-[1.3rem]">
        <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warn" aria-hidden />
        <p className="whitespace-pre-wrap text-pretty text-fg">{m.text}</p>
      </div>
    );
  }
  const ctx = m.author === "luca" ? contextLabel(m.context) : null;
  return (
    <div className="mt-0.5">
      {m.text && <p className="max-w-[72ch] whitespace-pre-wrap text-pretty text-sm leading-[1.35rem] text-fg">{m.text}</p>}
      {m.action && <ActionCard action={m.action} compact={compact} />}
      {(m.refs.length > 0 || ctx) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {ctx && <span className="inline-flex h-5 items-center rounded-tag px-1 text-2xs text-fg-subtle">da {ctx}</span>}
          {m.refs.map((r) => (
            <RefTag key={`${r.type}:${r.id}`} refItem={r} />
          ))}
        </div>
      )}
    </div>
  );
}

function PendingBody({ p }: { p: PendingSend }) {
  const { retry, discard, contextLabel } = useBridge();
  const ctx = contextLabel(p.context);
  return (
    <div className="mt-0.5">
      <p className={cn("max-w-[72ch] whitespace-pre-wrap text-pretty text-sm leading-[1.35rem]", p.failed ? "text-fg-muted" : "text-fg")}>{p.text}</p>
      {ctx && <p className="mt-1 text-2xs text-fg-subtle">da {ctx}</p>}
      {p.failed ? (
        <div role="alert" className="mt-1.5 max-w-[60ch] rounded-item bg-warn-soft px-2.5 py-2 text-xs leading-4">
          <p className="font-medium text-fg">Non inviato</p>
          <ul className="mt-0.5 text-fg-muted">
            {p.failed.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <div className="mt-1.5 flex gap-1">
            <button type="button" onClick={() => retry(p.key)} className="inline-flex h-6 items-center gap-1 rounded-item px-1.5 text-fg-muted hover:bg-hover hover:text-fg">
              <RotateCw className="size-3" /> Riprova
            </button>
            <button type="button" onClick={() => discard(p.key)} className="inline-flex h-6 items-center gap-1 rounded-item px-1.5 text-fg-muted hover:bg-hover hover:text-fg">
              <X className="size-3" /> Scarta
            </button>
          </div>
        </div>
      ) : (
        <p className="mt-1 inline-flex items-center gap-1 text-2xs text-fg-subtle">
          <Loader2 className="size-3 animate-spin" aria-hidden /> Invio…
        </p>
      )}
    </div>
  );
}

function GroupRow({ g, compact }: { g: Group; compact: boolean }) {
  const a = author(g.author);
  const ms = parseTs(g.firstTs);
  return (
    <li className={cn("row-arrive flex items-start gap-3 py-1.5", compact ? "px-3" : "px-5")}>
      <AuthorChip author={a} size={compact ? "sm" : "md"} className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-[13px] font-semibold text-fg">{a.name}</span>
          {g.relay && <span className="text-2xs text-fg-subtle">risposta inoltrata dal Bridge</span>}
          {ms !== null && (
            <time className="num text-2xs text-fg-subtle" dateTime={g.firstTs}>
              {timeFmt.format(new Date(ms))}
            </time>
          )}
        </div>
        {g.items.map((it) => (it.kind === "message" ? <MessageBody key={`m${it.m.id}`} m={it.m} compact={compact} /> : <PendingBody key={it.p.key} p={it.p} />))}
      </div>
    </li>
  );
}

/** "Sta pensando" / "Usa get_positions": the turn in progress, signed by the Bridge. */
export function TurnLine({ turn, compact }: { turn: LiveTurn; compact?: boolean }) {
  return (
    <div role="status" aria-live="polite" className={cn("flex items-center gap-3 py-2", compact ? "px-3" : "px-5")}>
      <span className="relative grid size-7 shrink-0 place-items-center" aria-hidden>
        <span className="agent-working size-2 rounded-full bg-[var(--author-bridge)]" />
      </span>
      <p className="flex min-w-0 items-center gap-1.5 text-xs text-fg-muted">
        {turn.status === "tool" ? (
          <>
            <Wrench className="size-3.5 shrink-0 text-fg-subtle" aria-hidden />
            <span>Il Bridge usa</span>
            <code className="truncate rounded-tag bg-hover px-1 font-mono text-2xs text-fg">{turn.tool ?? "un tool"}</code>
          </>
        ) : (
          <span>Il Bridge sta pensando…</span>
        )}
      </p>
    </div>
  );
}

type ThreadProps = {
  conversationId: number | null;
  compact?: boolean;
  /** What a new or empty conversation shows instead of messages. */
  empty?: ReactNode;
  /** Above the messages, scrolling with them (the Assistente's briefing on a new conversation). */
  lead?: ReactNode;
  className?: string;
  onConversation?: (c: Conversation | null) => void;
};

/** One Bridge conversation, anchored to the bottom like a chat: messages, relays, action cards, the live turn. */
export function Thread({ conversationId, compact = false, empty, lead, className, onConversation }: ThreadProps) {
  const q = useConversation(conversationId);
  const down = useRuntimeDown();
  const { live, pending } = useBridge();
  const now = useNow(60_000);
  const listRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const conv = q.data?.state === "ok" ? q.data.data : null;

  useEffect(() => {
    onConversation?.(conv);
  }, [conv, onConversation]);

  const items = useMemo<Item[]>(() => {
    const msgs = [...(conv?.messages ?? [])].sort((a, b) => (parseTs(a.ts) ?? 0) - (parseTs(b.ts) ?? 0) || a.id - b.id);
    const mine = pending.filter((p) => p.conversationId === conversationId);
    return [...msgs.map<Item>((m) => ({ kind: "message", m })), ...mine.map<Item>((p) => ({ kind: "pending", p }))];
  }, [conv, pending, conversationId]);
  const groups = useMemo(() => group(items, now), [items, now]);
  const turn = turnOf(conversationId, live, conv?.status);

  useEffect(() => {
    stick.current = true;
  }, [conversationId]);
  useLayoutEffect(() => {
    const el = listRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [items.length, conversationId, turn?.status, turn?.tool]);

  let body: ReactNode;
  if (conversationId !== null && q.isPending && down) {
    body = <p className={cn("py-3 text-xs leading-relaxed text-fg-subtle", compact ? "px-3" : "px-5")}>Runtime irraggiungibile: la conversazione torna appena risponde.</p>;
  } else if (conversationId !== null && q.isPending) {
    body = (
      <ul className={cn("space-y-4 py-3", compact ? "px-3" : "px-5")} aria-busy aria-label="Caricamento della conversazione">
        {[0, 1, 2].map((i) => (
          <li key={i} className="flex gap-3">
            <span className="size-7 shrink-0 animate-pulse rounded-full bg-hover" />
            <span className="flex-1 space-y-2 pt-1">
              <span className="block h-3 w-32 animate-pulse rounded-tag bg-hover" />
              <span className={cn("block h-3 animate-pulse rounded-tag bg-hover", i === 1 ? "w-3/5" : "w-4/5")} />
            </span>
          </li>
        ))}
      </ul>
    );
  } else if (q.isError) {
    body = <p className={cn("py-3 text-xs text-warn", compact ? "px-3" : "px-5")}>Conversazione non disponibile: {q.error.message}</p>;
  } else if (q.data?.state === "unavailable") {
    body = (
      <p className={cn("py-3 text-xs text-fg-muted", compact ? "px-3" : "px-5")}>
        Il Runtime non espone ancora <code className="font-mono text-2xs text-fg">{q.data.endpoint}</code>.
      </p>
    );
  } else if (groups.length === 0) {
    body = empty ?? null;
  } else {
    body = (
      <ol aria-live="polite" aria-relevant="additions" aria-label="Messaggi">
        {groups.map((g, i) => (
          <li key={`${g.firstTs}-${i}`} className="list-none">
            {(i === 0 || groups[i - 1].day !== g.day) && <p className="pb-1 pt-3 text-center text-2xs font-medium text-fg-subtle first:pt-1">{g.day}</p>}
            <ul>
              <GroupRow g={g} compact={compact} />
            </ul>
          </li>
        ))}
      </ol>
    );
  }

  return (
    <div
      ref={listRef}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
      }}
      className={cn("min-h-0 flex-1 overflow-y-auto", className)}
    >
      <div className="flex min-h-full flex-col">
        {lead}
        <div className={cn("flex flex-1 flex-col pb-2", groups.length > 0 ? "justify-end" : "justify-center")}>
          {body}
          {turn && <TurnLine turn={turn} compact={compact} />}
        </div>
      </div>
    </div>
  );
}
