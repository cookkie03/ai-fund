import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, MoreHorizontal, PanelLeftClose, Pencil, Search, SquarePen, X } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { IconButton } from "@/components/tile";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { author } from "@/lib/authors";
import { fmtWhen } from "@/lib/format";
import { CommandRefused } from "@/lib/runtime/hooks";
import { useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { toast } from "sonner";
import { useConversations, useRuntimeDown } from "./hooks";
import { useBridge } from "./state";
import { turnOf } from "./thread";
import type { ConversationSummary } from "./types";

function useConversationCommand<N extends "bridge_rename_conversation" | "bridge_archive_conversation">(name: N) {
  const { client } = useRuntime();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: N extends "bridge_rename_conversation" ? { conversation_id: number; title: string } : { conversation_id: number; archived: boolean }) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const res = await client.command(name, payload as any);
      if (!res.ok) throw new CommandRefused(res.reasons);
      return res;
    },
    onError: (err) => toast.error("Il Runtime ha rifiutato il comando", { description: err instanceof CommandRefused ? err.reasons.join(" · ") : err.message }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["bridge"] }),
  });
}

function Row({ c, selected, onSelect }: { c: ConversationSummary; selected: boolean; onSelect: () => void }) {
  const { live } = useBridge();
  const { writable } = useShell();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(c.title);
  const input = useRef<HTMLInputElement>(null);
  const rename = useConversationCommand("bridge_rename_conversation");
  const archive = useConversationCommand("bridge_archive_conversation");
  const turn = turnOf(c.id, live, c.status);
  const last = c.last_message;

  useEffect(() => {
    if (editing) requestAnimationFrame(() => input.current?.select());
  }, [editing]);

  const commit = () => {
    const t = title.trim();
    setEditing(false);
    if (t && t !== c.title) rename.mutate({ conversation_id: c.id, title: t });
    else setTitle(c.title);
  };

  return (
    <li className="group/row relative">
      {editing ? (
        <div className="px-1.5 py-1">
          <input
            ref={input}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") {
                setTitle(c.title);
                setEditing(false);
              }
            }}
            aria-label="Nuovo titolo della conversazione"
            className="h-8 w-full rounded-item border border-accent-c/70 bg-[oklch(0.205_0.008_260)] px-2 text-sm text-fg outline-none"
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={onSelect}
          aria-current={selected ? "true" : undefined}
          className={cn(
            "flex w-full flex-col gap-0.5 rounded-item px-2.5 py-2 pr-9 text-left transition-colors duration-150",
            selected ? "bg-selected shadow-[inset_0_0.5px_0_oklch(1_0_0/0.06)]" : "hover:bg-hover",
          )}
        >
          <span className="flex w-full items-center gap-1.5">
            {turn && <span className="agent-working size-1.5 shrink-0 rounded-full bg-[var(--author-bridge)]" aria-label="Turno in corso" />}
            <span className={cn("min-w-0 flex-1 truncate text-[13px]", selected ? "font-semibold text-fg" : "font-medium text-fg")}>{c.title || "Senza titolo"}</span>
            <time className="num shrink-0 text-2xs text-fg-subtle" dateTime={c.updated_ts}>
              {fmtWhen(c.updated_ts)}
            </time>
          </span>
          <span className="flex w-full items-center gap-1.5">
            <span className="min-w-0 flex-1 truncate text-xs text-fg-subtle">
              {turn ? (
                <span className="text-fg-muted">{turn.status === "tool" && turn.tool ? `Usa ${turn.tool}…` : "Sta pensando…"}</span>
              ) : last ? (
                <>
                  <span className="text-fg-muted">{last.author === "luca" ? "Tu" : author(last.author).short}:</span> {last.text}
                </>
              ) : (
                "Nessun messaggio"
              )}
            </span>
            {c.pending_actions > 0 && (
              <span className="num shrink-0 rounded-tag bg-warn-soft px-1.5 text-[10px] font-medium leading-4 text-warn" title={`${c.pending_actions} da confermare`}>
                {c.pending_actions} da confermare
              </span>
            )}
          </span>
        </button>
      )}
      {!editing && (
        <DropdownMenu>
          <DropdownMenuTrigger
            disabled={!writable}
            className="absolute right-1.5 top-1.5 grid size-6 place-items-center rounded-item text-fg-subtle opacity-0 transition-opacity hover:bg-hover hover:text-fg focus-visible:opacity-100 group-hover/row:opacity-100 data-[state=open]:opacity-100 [@media(pointer:coarse)]:opacity-100"
            aria-label={`Azioni per ${c.title}`}
          >
            <MoreHorizontal className="size-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuItem onSelect={() => setEditing(true)} className="gap-2">
              <Pencil className="size-3.5" /> Rinomina
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => archive.mutate({ conversation_id: c.id, archived: !c.archived })} className="gap-2">
              {c.archived ? <ArchiveRestore className="size-3.5" /> : <Archive className="size-3.5" />}
              {c.archived ? "Ripristina" : "Archivia"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </li>
  );
}

/** The Claude app's sidebar inside a tile: new conversation, search, the list by latest activity, archive. */
export function ConversationList({ onHide, onPicked, className, style }: { onHide?: () => void; onPicked?: () => void; className?: string; style?: CSSProperties }) {
  const { currentId, select } = useBridge();
  const down = useRuntimeDown();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [archived, setArchived] = useState(false);
  const list = useConversations({ q: query, archived });

  // Search as you type, one request per pause.
  useEffect(() => {
    const t = setTimeout(() => setQuery(q.trim()), 220);
    return () => clearTimeout(t);
  }, [q]);

  const rows = list.data?.state === "ok" ? list.data.data : [];
  const pick = (id: number | null) => {
    select(id);
    onPicked?.();
  };

  return (
    <nav aria-label="Conversazioni con il Bridge" data-region="conversations" className={cn("flex min-h-0 flex-col bg-ground", className)} style={style}>
      <header className="flex h-11 shrink-0 items-center gap-1 pl-4 pr-2">
        <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">Conversazioni</h2>
        <div className="ml-auto flex items-center gap-0.5">
          <IconButton icon={SquarePen} label="Nuova conversazione" onClick={() => pick(null)} active={currentId === null} />
          {onHide && <IconButton icon={PanelLeftClose} label="Nascondi le conversazioni" shortcut="Ctrl/⌘ B" onClick={onHide} />}
        </div>
      </header>
      <div className="px-2.5 pb-2">
        <label className="flex h-8 items-center gap-2 rounded-control bg-[oklch(0_0_0/0.25)] px-2.5 shadow-[inset_0_0_0_1px_oklch(1_0_0/0.04)] focus-within:shadow-[inset_0_0_0_1px_var(--accent-c)]">
          <Search className="size-3.5 shrink-0 text-fg-subtle" aria-hidden />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Cerca in titoli e messaggi"
            aria-label="Cerca nelle conversazioni"
            className="min-w-0 flex-1 bg-transparent text-xs text-fg outline-none placeholder:text-fg-subtle"
          />
          {q && (
            <button type="button" onClick={() => setQ("")} aria-label="Cancella la ricerca" className="grid size-5 place-items-center rounded-tag text-fg-subtle hover:text-fg">
              <X className="size-3" />
            </button>
          )}
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-1.5">
        {list.isPending && down ? (
          <p className="px-2.5 py-2 text-xs leading-relaxed text-fg-subtle">Runtime irraggiungibile: le conversazioni tornano appena risponde.</p>
        ) : list.isPending ? (
          <ul className="space-y-1 px-1" aria-busy aria-label="Caricamento delle conversazioni">
            {[0, 1, 2, 3].map((i) => (
              <li key={i} className="space-y-1.5 rounded-item px-2.5 py-2">
                <span className="block h-3 w-3/4 animate-pulse rounded-tag bg-hover" />
                <span className="block h-2.5 w-full animate-pulse rounded-tag bg-hover" />
              </li>
            ))}
          </ul>
        ) : list.isError ? (
          <p className="px-2.5 py-2 text-xs text-warn">Elenco non disponibile: {list.error.message}</p>
        ) : list.data?.state === "unavailable" ? (
          <div className="px-2.5 py-2 text-xs leading-relaxed text-fg-muted">
            <p className="font-medium text-fg">Bridge non disponibile</p>
            <p className="mt-1">
              Il Runtime non espone ancora <code className="font-mono text-2xs text-fg">{list.data.endpoint}</code>: le conversazioni arrivano con il Bridge agent.
            </p>
          </div>
        ) : rows.length === 0 ? (
          <p className="px-2.5 py-2 text-xs leading-relaxed text-fg-subtle">
            {query ? `Nessuna conversazione contiene «${query}».` : archived ? "Nessuna conversazione archiviata." : "Ancora nessuna conversazione. La prima si apre quando scrivi al Bridge."}
          </p>
        ) : (
          <ul className={cn("space-y-0.5 transition-opacity", list.isPlaceholderData && "opacity-60")}>
            {rows.map((c) => (
              <Row key={c.id} c={c} selected={c.id === currentId} onSelect={() => pick(c.id)} />
            ))}
          </ul>
        )}
      </div>
      <footer className="shrink-0 px-2.5 pb-2.5 pt-1">
        <button
          type="button"
          onClick={() => setArchived((a) => !a)}
          aria-pressed={archived}
          className={cn("inline-flex h-7 items-center gap-1.5 rounded-item px-2 text-xs transition-colors", archived ? "bg-hover text-fg" : "text-fg-subtle hover:bg-hover hover:text-fg")}
        >
          <Archive className="size-3.5" /> {archived ? "Torna alle conversazioni" : "Archiviate"}
        </button>
      </footer>
    </nav>
  );
}
