import { ArrowUp, Hash, MessageCircle } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { AuthorChip } from "@/components/author-chip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { COCKPIT_TOPIC, topicTitle } from "@/features/office/api";
import { useChat } from "@/features/office/hooks";
import { author } from "@/lib/authors";
import { parseTs } from "@/lib/format";
import { CommandRefused, useCommand } from "@/lib/runtime/hooks";
import { useNow } from "@/lib/runtime/provider";
import type { Message } from "@/lib/runtime/types";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";

const dayFmt = new Intl.DateTimeFormat("it-IT", { weekday: "long", day: "numeric", month: "long" });
const timeFmt = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" });

function dayLabel(ms: number, now: number): string {
  const d = new Date(ms);
  const today = new Date(now);
  if (d.toDateString() === today.toDateString()) return "Oggi";
  const y = new Date(now);
  y.setDate(y.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return "Ieri";
  return dayFmt.format(d);
}

type Group = { day: string; author: string; first: Message; items: Message[] };

/** Slack's rule: consecutive messages by the same author within 5 minutes share one header. */
function group(messages: Message[], now: number): Group[] {
  const out: Group[] = [];
  for (const m of messages) {
    const ms = parseTs(m.ts) ?? 0;
    const day = dayLabel(ms, now);
    const last = out.at(-1);
    const lastMs = last ? parseTs(last.items.at(-1)!.ts) ?? 0 : 0;
    if (last && last.author === m.author && last.day === day && ms - lastMs < 5 * 60_000 && m.kind === last.first.kind) last.items.push(m);
    else out.push({ day, author: m.author, first: m, items: [m] });
  }
  return out;
}

export function TopicIcon({ topic, className }: { topic: string; className?: string }) {
  const Icon = topic === COCKPIT_TOPIC ? MessageCircle : Hash;
  return <Icon className={cn("size-3.5 shrink-0", className)} strokeWidth={1.75} aria-hidden />;
}

function MessageGroup({ g, agent }: { g: Group; agent: string }) {
  const a = author(g.author);
  const summary = g.first.kind === "summary";
  return (
    <li className="group/msg flex gap-3 px-4 py-1.5">
      <AuthorChip author={a} size="md" className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-[13px] font-semibold text-fg">{a.name}</span>
          {a.kind === "human" && <span className="text-2xs text-fg-subtle">via {a.channel ?? "cockpit"}</span>}
          {a.kind === "agent" && a.id !== agent && <span className="text-2xs text-fg-subtle">da un altro agente</span>}
          <time className="num text-2xs text-fg-subtle" dateTime={g.first.ts}>
            {timeFmt.format(new Date(parseTs(g.first.ts) ?? 0))}
          </time>
          {summary && <span className="rounded-tag bg-hover px-1.5 text-[10px] leading-4 text-fg-muted">Riassunto</span>}
          {g.first.cycle_id !== null && <span className="num text-2xs text-fg-subtle">ciclo #{g.first.cycle_id}</span>}
        </div>
        {g.items.map((m) => (
          <p key={m.id} className={cn("mt-0.5 max-w-[72ch] whitespace-pre-wrap text-pretty text-sm leading-[1.35rem]", summary ? "text-fg-muted" : "text-fg")}>
            {m.text}
          </p>
        ))}
      </div>
    </li>
  );
}

function Composer({ agent, topic }: { agent: string; topic: string }) {
  const { writable } = useShell();
  const [text, setText] = useState("");
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const say = useCommand("say", { invalidate: [["office", "chat"], ["office", "topics"]], toastRefusal: false });
  const name = author(agent).short;
  const where = topic === COCKPIT_TOPIC ? "nella vostra chat" : `in ${topicTitle(topic)}`;

  useEffect(() => {
    setRefusal(null);
  }, [agent, topic]);

  // The field grows with the text up to ~8 lines.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 176)}px`;
  }, [text]);

  const body = text.trim();
  const canSend = writable && body.length > 0 && !say.isPending;
  const send = () => {
    if (!canSend) return;
    setRefusal(null);
    say.mutate(
      { agent, chat: topic, text: body },
      {
        onSuccess: () => setText(""),
        onError: (err) => {
          if (err instanceof CommandRefused) setRefusal(err.reasons.length ? err.reasons : ["Nessuna ragione indicata"]);
        },
      },
    );
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="shrink-0 px-3 pb-3 pt-1">
      {refusal && (
        <Alert variant="warning" className="mb-2">
          <AlertTitle>Il Runtime non ha accettato il messaggio</AlertTitle>
          <AlertDescription>
            <ul className="mt-0.5">
              {refusal.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      <div className="rounded-control border border-line-strong bg-raised transition-colors focus-within:border-accent-c/70">
        <Textarea
          ref={ref}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          disabled={!writable}
          placeholder={writable ? `Scrivi a ${name} ${where}` : "Runtime irraggiungibile: invio sospeso"}
          aria-label={`Messaggio a ${author(agent).name}`}
          className="block min-h-[44px] w-full resize-none border-none bg-transparent px-3 pt-3 text-sm leading-5 text-fg shadow-none outline-none focus-visible:ring-0 placeholder:text-fg-subtle disabled:cursor-not-allowed"
        />
        <div className="flex items-center gap-2 pb-2 pl-3 pr-2">
          <span className="min-w-0 truncate text-2xs text-fg-subtle">{name} lo pesa come il parere di un collega: può non essere d'accordo e dirti perché.</span>
          <span className="ml-auto hidden shrink-0 text-2xs text-fg-subtle lg:inline">
            <kbd className="rounded-tag bg-hover px-1 font-sans">Invio</kbd> invia · <kbd className="rounded-tag bg-hover px-1 font-sans">Maiusc Invio</kbd> a capo
          </span>
          <Button size="icon-sm" className="ml-auto shrink-0 lg:ml-1" disabled={!canSend} onClick={send} aria-label="Invia" data-action="send">
            <ArrowUp />
          </Button>
        </div>
      </div>
    </div>
  );
}

/** The selected chat, Claude-app style: every message signed, the composer docked at the bottom. */
export function Conversation({ agent, topic, header, className }: { agent: string; topic: string; header?: ReactNode; className?: string }) {
  const q = useChat(agent, topic);
  const now = useNow(60_000);
  const listRef = useRef<HTMLDivElement>(null);
  const messages = useMemo(() => [...(q.data ?? [])].sort((a, b) => (parseTs(a.ts) ?? 0) - (parseTs(b.ts) ?? 0) || a.id - b.id), [q.data]);
  const groups = useMemo(() => group(messages, now), [messages, now]);
  const stick = useRef(true);

  // Open at the latest message; keep following new ones only while the reader is at the bottom.
  useEffect(() => {
    stick.current = true;
  }, [agent, topic]);
  useLayoutEffect(() => {
    const el = listRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages.length, agent, topic]);

  const name = author(agent).short;

  return (
    <section aria-label={`Chat ${topicTitle(topic)} di ${author(agent).name}`} className={cn("flex min-h-0 min-w-0 flex-col bg-ground", className)}>
      {header}
      <div
        ref={listRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
        }}
        className="min-h-0 flex-1 overflow-y-auto py-2"
      >
        {q.isPending ? (
          <ul className="space-y-4 px-4 py-2" aria-busy aria-label="Caricamento della chat">
            {[0, 1, 2].map((i) => (
              <li key={i} className="flex gap-3">
                <span className="size-7 shrink-0 animate-pulse rounded-full bg-hover" />
                <span className="flex-1 space-y-2 pt-1">
                  <span className="block h-3 w-40 animate-pulse rounded-tag bg-hover" />
                  <span className="block h-3 w-4/5 animate-pulse rounded-tag bg-hover" />
                </span>
              </li>
            ))}
          </ul>
        ) : q.isError ? (
          <p className="px-4 py-3 text-xs text-down">Chat non disponibile: {q.error.message}</p>
        ) : messages.length === 0 ? (
          <div className="grid h-full place-items-center px-6 text-center">
            <div className="max-w-[40ch]">
              <TopicIcon topic={topic} className="mx-auto size-5 text-fg-subtle" />
              <p className="mt-3 text-sm text-fg">{topic === COCKPIT_TOPIC ? `Nessun messaggio tra te e ${name}.` : `${topicTitle(topic)} è vuota.`}</p>
              <p className="mt-1 text-xs leading-relaxed text-fg-subtle">Scrivi qui sotto: il messaggio entra nella chat di {name} e lo legge al prossimo turno.</p>
            </div>
          </div>
        ) : (
          <ol aria-live="polite" aria-relevant="additions" className="flex min-h-full flex-col justify-end">
            {groups.map((g, i) => (
              <li key={g.first.id} className="list-none">
                {(i === 0 || groups[i - 1].day !== g.day) && (
                  <p className="px-4 pb-1 pt-3 text-center text-2xs font-medium text-fg-subtle first:pt-1">{g.day}</p>
                )}
                <ul>
                  <MessageGroup g={g} agent={agent} />
                </ul>
              </li>
            ))}
          </ol>
        )}
      </div>
      <Composer agent={agent} topic={topic} />
    </section>
  );
}

