import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, AtSign, Square, X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { COCKPIT_TOPIC } from "@/features/office/api";
import { AGENTS, AGENT_IDS } from "@/lib/authors";
import { CommandRefused, useCommand } from "@/lib/runtime/hooks";
import { useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { useBridge } from "./state";
import type { BridgeContext } from "./types";

/** `@agent` anywhere at a word start: the Bridge is asked to write to that agent. */
const MENTION_AT_CURSOR = /(^|\s)@([a-z_]*)$/i;
const FIRST_MENTION = /(?:^|\s)@([a-z_]+)\b/i;

export function mentionedAgent(text: string): string | null {
  const m = text.match(FIRST_MENTION);
  return m && AGENTS[m[1].toLowerCase()] ? m[1].toLowerCase() : null;
}

type Props = {
  conversationId: number | null;
  /** Context attached to the next message (the page, or a briefing item). */
  context: BridgeContext | null;
  onDropContext?: () => void;
  /** A turn is running in this conversation: Stop replaces Invia while the field is empty (a new message joins the next turn). */
  turnActive?: boolean;
  compact?: boolean;
  autoFocus?: boolean;
  className?: string;
};

/** Claude-app composer: grows to 8 lines, Invio sends, Maiusc Invio breaks the line, @ picks an agent. */
export function BridgeComposer({ conversationId, context, onDropContext, turnActive = false, compact = false, autoFocus = false, className }: Props) {
  const { writable } = useShell();
  const { client } = useRuntime();
  const qc = useQueryClient();
  const bridge = useBridge();
  const fallback = bridge.availability === "unavailable";
  const [text, setText] = useState("");
  const [menu, setMenu] = useState<{ query: string; index: number } | null>(null);
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const say = useCommand("say", { invalidate: [["cycles"], ["office", "chat"]], toastRefusal: false });
  const stop = useMutation({
    mutationFn: async () => {
      if (conversationId === null) return;
      const res = await client.command("bridge_stop", { conversation_id: conversationId });
      if (!res.ok) throw new CommandRefused(res.reasons);
    },
    onError: (err) => setRefusal(err instanceof CommandRefused ? err.reasons : [err.message]),
    onSettled: () => qc.invalidateQueries({ queryKey: ["bridge"] }),
  });

  useEffect(() => {
    if (!bridge.seed) return;
    setText(bridge.seed.text);
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(bridge.seed!.text.length, bridge.seed!.text.length);
    });
  }, [bridge.seed]);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus, conversationId]);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 176)}px`;
  }, [text]);

  const body = text.trim();
  const agent = mentionedAgent(text);
  const options = menu ? AGENT_IDS.filter((id) => id.includes(menu.query) || AGENTS[id].name.toLowerCase().includes(menu.query) || AGENTS[id].short.toLowerCase().includes(menu.query)) : [];
  const canSend = writable && body.length > 0 && (fallback ? !!agent && !say.isPending : bridge.availability === "ready");

  const send = () => {
    if (!canSend) return;
    setRefusal(null);
    if (fallback) {
      // Without the Bridge, `@agent` writes straight into that agent's "cockpit" chat, as before.
      const clean = body.replace(new RegExp(`(^|\\s)@${agent}\\b`, "i"), " ").trim();
      say.mutate(
        { agent: agent!, chat: COCKPIT_TOPIC, text: clean },
        {
          onSuccess: () => setText(""),
          onError: (err) => setRefusal(err instanceof CommandRefused ? (err.reasons.length ? err.reasons : ["Nessuna ragione indicata"]) : [err.message]),
        },
      );
      return;
    }
    void bridge.send(body, { conversationId, context });
    setText("");
  };

  const pick = (id: string) => {
    const el = ref.current;
    const at = el?.selectionStart ?? text.length;
    const before = text.slice(0, at).replace(MENTION_AT_CURSOR, (_m, sp) => `${sp}@${id} `);
    setText(before + text.slice(at));
    setMenu(null);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(before.length, before.length);
    });
  };

  const onChange = (value: string, caret: number) => {
    setText(value);
    const m = value.slice(0, caret).match(MENTION_AT_CURSOR);
    setMenu(m ? { query: m[2].toLowerCase(), index: 0 } : null);
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
        e.preventDefault();
        setMenu(null);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  const placeholder = !writable
    ? "Runtime irraggiungibile: invio sospeso"
    : fallback
      ? "@agente scrivi un messaggio…"
      : conversationId === null
        ? "Chiedi al Bridge, o @agente per scrivere a un agente"
        : "Rispondi al Bridge";

  return (
    <div className={cn("relative shrink-0", compact ? "p-2.5" : "px-4 pb-4 pt-1", className)}>
      {refusal && (
        <div role="alert" className="mb-2 rounded-item bg-warn-soft px-3 py-2 text-xs leading-4">
          <p className="font-medium text-fg">Il Runtime non ha accettato il comando</p>
          <ul className="mt-0.5 text-fg-muted">
            {refusal.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {menu && options.length > 0 && (
        <ul
          role="listbox"
          aria-label="Agenti"
          className={cn("absolute bottom-full z-20 mb-1 overflow-hidden rounded-tile border border-line-strong/70 bg-raised p-1.5 shadow-[0_16px_40px_-12px_oklch(0_0_0/0.75)]", compact ? "inset-x-2.5" : "inset-x-4 max-w-sm")}
        >
          {options.map((id, i) => (
            <li key={id} role="option" aria-selected={i === menu.index}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(id);
                }}
                className={cn("flex w-full items-center gap-2 rounded-item px-2.5 py-1.5 text-left text-xs", i === menu.index ? "bg-hover text-fg" : "text-fg-muted")}
              >
                <AuthorChip actor={id} size="xs" tooltip={AGENTS[id].name} />
                <span>{AGENTS[id].name}</span>
                <span className="ml-auto text-fg-subtle">@{id}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="rounded-control border border-line-strong bg-[oklch(0.205_0.008_260)] transition-colors focus-within:border-accent-c/70">
        {context && !fallback && (
          <div className="flex items-center gap-1.5 px-3 pt-2 text-2xs text-fg-subtle">
            <span>Contesto</span>
            <span className="inline-flex h-5 max-w-[30ch] items-center gap-1 rounded-tag bg-hover pl-1.5 pr-0.5 text-fg-muted">
              <span className="truncate">{bridge.contextLabel(context) ?? context.page}</span>
              {onDropContext && (
                <button type="button" onClick={onDropContext} className="grid size-4 place-items-center rounded-tag text-fg-subtle hover:bg-selected hover:text-fg" aria-label="Togli il contesto">
                  <X className="size-3" />
                </button>
              )}
            </span>
          </div>
        )}
        <textarea
          ref={ref}
          value={text}
          onChange={(e) => onChange(e.target.value, e.target.selectionStart)}
          onKeyDown={onKeyDown}
          rows={1}
          disabled={!writable}
          placeholder={placeholder}
          aria-label={fallback ? "Messaggio a un agente" : "Messaggio al Bridge"}
          className={cn(
            "block w-full resize-none bg-transparent px-3 text-sm leading-5 text-fg outline-none placeholder:text-fg-subtle disabled:cursor-not-allowed",
            compact ? "min-h-[40px] pt-2.5" : "min-h-[48px] pt-3",
          )}
        />
        <div className="flex items-center gap-2 pb-2 pl-2 pr-2">
          {agent ? (
            <span className="inline-flex min-w-0 items-center gap-1.5 truncate text-2xs text-fg-subtle">
              {fallback ? "A" : "Il Bridge scriverà a"} <AuthorChip actor={agent} size="xs" label />
            </span>
          ) : (
            <button
              type="button"
              disabled={!writable}
              onClick={() => {
                const next = text && !/\s$/.test(text) ? `${text} @` : `${text}@`;
                setText(next);
                setMenu({ query: "", index: 0 });
                requestAnimationFrame(() => {
                  ref.current?.focus();
                  ref.current?.setSelectionRange(next.length, next.length);
                });
              }}
              className="inline-flex h-6 shrink-0 items-center gap-1 rounded-item px-1 text-2xs text-fg-subtle transition-colors hover:bg-hover hover:text-fg disabled:opacity-50"
            >
              <AtSign className="size-3.5" /> {fallback ? "Scegli un agente" : "Agente"}
            </button>
          )}
          {!compact && (
            <span className="ml-auto hidden shrink-0 text-2xs text-fg-subtle lg:inline">
              <kbd className="rounded-tag bg-hover px-1 font-sans">Invio</kbd> invia · <kbd className="rounded-tag bg-hover px-1 font-sans">Maiusc Invio</kbd> a capo
            </span>
          )}
          {turnActive && !fallback && body.length === 0 ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="icon-sm"
                  variant="outline"
                  className={cn("shrink-0", compact ? "ml-auto" : "ml-auto lg:ml-1")}
                  disabled={!writable || stop.isPending}
                  onClick={() => stop.mutate()}
                  aria-label="Ferma il turno del Bridge"
                  data-action="stop"
                >
                  <Square className="size-3 fill-current" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Ferma il turno: il Bridge si interrompe al passo successivo</TooltipContent>
            </Tooltip>
          ) : (
            <Button size="icon-sm" className={cn("shrink-0", compact ? "ml-auto" : "ml-auto lg:ml-1")} disabled={!canSend} onClick={send} aria-label="Invia" data-action="send">
              <ArrowUp />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
