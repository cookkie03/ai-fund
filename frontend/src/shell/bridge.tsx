import { useQueries } from "@tanstack/react-query";
import { ArrowUp, AtSign, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { AGENTS, AGENT_IDS, author } from "@/lib/authors";
import { fmtWhen, parseTs } from "@/lib/format";
import { useCommand } from "@/lib/runtime/hooks";
import { useRuntime } from "@/lib/runtime/provider";
import type { Message } from "@/lib/runtime/types";
import { cn } from "@/lib/utils";
import { useShell } from "./shell-state";

/** Chat topic the cockpit writes into for each agent. */
export const COCKPIT_TOPIC = "cockpit";

function useCockpitThreads() {
  const { client, target } = useRuntime();
  const results = useQueries({
    queries: AGENT_IDS.map((agent) => ({
      queryKey: ["cycles", target.id, "chat", agent, COCKPIT_TOPIC],
      queryFn: () => client.read<Message[]>("chat", { agent, topic: COCKPIT_TOPIC, limit: 100 }),
      staleTime: 10_000,
    })),
  });
  const messages = useMemo(
    () =>
      results
        .flatMap((r, i) => (r.data ?? []).map((m) => ({ ...m, agent: AGENT_IDS[i] })))
        .sort((a, b) => (parseTs(a.ts) ?? 0) - (parseTs(b.ts) ?? 0)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [results.map((r) => r.dataUpdatedAt).join()],
  );
  return { messages, loading: results.some((r) => r.isPending), error: results.every((r) => r.isError) };
}

const MENTION = /^@([a-z_]+)\s+/;

function parseMention(text: string): { agent: string | null; body: string } {
  const m = text.match(MENTION);
  if (m && AGENTS[m[1]]) return { agent: m[1], body: text.slice(m[0].length).trim() };
  return { agent: null, body: text.trim() };
}

export function BridgePanel({ onClose, className }: { onClose?: () => void; className?: string }) {
  const { composerSeed, writable } = useShell();
  const { messages, loading, error } = useCockpitThreads();
  const [text, setText] = useState("");
  const [menu, setMenu] = useState<{ query: string; index: number } | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const say = useCommand("say", { invalidate: [["cycles"]] });

  useEffect(() => {
    if (!composerSeed) return;
    setText(composerSeed.text);
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(composerSeed.text.length, composerSeed.text.length);
    });
  }, [composerSeed]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages.length]);

  const { agent, body } = parseMention(text);
  const canSend = writable && !!agent && body.length > 0 && !say.isPending;
  const options = menu ? AGENT_IDS.filter((id) => id.includes(menu.query) || AGENTS[id].name.toLowerCase().includes(menu.query)) : [];

  const send = () => {
    if (!canSend || !agent) return;
    say.mutate({ agent, chat: COCKPIT_TOPIC, text: body }, { onSuccess: () => setText("") });
  };

  const pick = (id: string) => {
    setText((t) => `@${id} ${t.replace(/^@[a-z_]*\s*/i, "")}`);
    setMenu(null);
    inputRef.current?.focus();
  };

  const onChange = (value: string) => {
    setText(value);
    const m = value.match(/^@([a-z_]*)$/i);
    setMenu(m ? { query: m[1].toLowerCase(), index: 0 } : null);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (menu && options.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const d = e.key === "ArrowDown" ? 1 : -1;
        setMenu({ ...menu, index: (menu.index + d + options.length) % options.length });
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        pick(options[menu.index]);
        return;
      }
      if (e.key === "Escape") {
        setMenu(null);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <aside data-region="bridge-panel" aria-label="Bridge" className={cn("flex h-full min-h-0 flex-col bg-panel", className)}>
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-line px-3">
        <Sparkles className="size-4 text-accent-c" aria-hidden />
        <h2 className="text-sm font-medium">Bridge</h2>
        <span className="rounded bg-hover px-1.5 py-0.5 text-2xs text-fg-subtle">non ancora attivo</span>
        {onClose && (
          <Button variant="ghost" size="icon-sm" className="ml-auto" onClick={onClose} aria-label="Chiudi il Bridge">
            <X />
          </Button>
        )}
      </div>

      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <div className="mb-4 rounded-md border border-line px-3 py-3 text-xs leading-relaxed text-fg-muted">
          <p className="text-fg">Il Bridge sarà il tuo interlocutore nell'ufficio: legge tutto, parla con ogni agente e usa i tuoi stessi comandi.</p>
          <p className="mt-1.5">Finché non è attivo nel Runtime, scrivi direttamente a un agente con <span className="text-fg">@</span>: il messaggio arriva nella sua chat «{COCKPIT_TOPIC}» e lui lo pesa come il parere di un collega.</p>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {AGENT_IDS.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => {
                  setText(`@${id} `);
                  inputRef.current?.focus();
                }}
                className="inline-flex h-6 items-center gap-1.5 rounded border border-line px-1.5 text-2xs text-fg-muted transition-colors hover:border-line-strong hover:bg-hover hover:text-fg"
              >
                <AuthorChip actor={id} size="xs" tooltip={AGENTS[id].name} />
                {AGENTS[id].short}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[0, 1].map((i) => (
              <div key={i} className="h-12 animate-pulse rounded bg-hover" />
            ))}
          </div>
        ) : error ? (
          <p className="text-xs text-down">Impossibile leggere le chat dal Runtime.</p>
        ) : messages.length === 0 ? (
          <p className="text-xs text-fg-subtle">Nessun messaggio inviato dal cockpit.</p>
        ) : (
          <ol className="space-y-3.5">
            {messages.map((m) => {
              const a = author(m.author);
              return (
                <li key={`${m.agent}-${m.id}`} className="flex gap-2.5">
                  <AuthorChip author={a} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-1.5 text-2xs">
                      <span className="text-xs font-medium text-fg">{a.name}</span>
                      {a.kind === "human" && (
                        <span className="text-fg-subtle">
                          a <span className="text-fg-muted">{AGENTS[m.agent]?.short}</span>
                        </span>
                      )}
                      <span className="num ml-auto text-fg-subtle">{fmtWhen(m.ts)}</span>
                    </div>
                    <p className="mt-0.5 whitespace-pre-wrap text-sm leading-snug text-fg">{m.text}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      <div className="relative shrink-0 border-t border-line p-2.5">
        {menu && options.length > 0 && (
          <ul role="listbox" className="absolute inset-x-2.5 bottom-full mb-1 overflow-hidden rounded-md border border-line-strong bg-raised py-1 shadow-[0_10px_30px_-10px_rgb(0_0_0/0.7)]">
            {options.map((id, i) => (
              <li key={id} role="option" aria-selected={i === menu.index}>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pick(id);
                  }}
                  className={cn("flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs", i === menu.index ? "bg-hover text-fg" : "text-fg-muted")}
                >
                  <AuthorChip actor={id} size="xs" tooltip={AGENTS[id].name} />
                  <span>{AGENTS[id].name}</span>
                  <span className="ml-auto text-fg-subtle">@{id}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="rounded-md border border-line-strong bg-ground focus-within:border-accent-c/70">
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            placeholder={writable ? "@agente scrivi un messaggio…" : "Runtime irraggiungibile: invio sospeso"}
            disabled={!writable}
            aria-label="Messaggio a un agente"
            className="block max-h-40 w-full resize-none bg-transparent px-2.5 pt-2 text-sm text-fg outline-none placeholder:text-fg-subtle disabled:cursor-not-allowed"
          />
          <div className="flex items-center gap-2 px-2 pb-1.5">
            {agent ? (
              <span className="inline-flex items-center gap-1.5 text-2xs text-fg-subtle">
                A <AuthorChip actor={agent} size="xs" label />
              </span>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setText("@");
                  setMenu({ query: "", index: 0 });
                  inputRef.current?.focus();
                }}
                className="inline-flex h-6 items-center gap-1 rounded px-1 text-2xs text-fg-subtle hover:bg-hover hover:text-fg"
              >
                <AtSign className="size-3.5" /> Scegli un agente
              </button>
            )}
            <Button size="icon-sm" className="ml-auto size-7" disabled={!canSend} onClick={send} aria-label="Invia">
              <ArrowUp />
            </Button>
          </div>
        </div>
      </div>
    </aside>
  );
}
