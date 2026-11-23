import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, MessageSquareReply } from "lucide-react";
import { useState } from "react";
import { useBriefing, useRuntimeDown } from "@/features/bridge/hooks";
import { useBridge } from "@/features/bridge/state";
import type { Briefing as BriefingData, BriefingItem, Severity } from "@/features/bridge/types";
import { fmtMoney, fmtPct, fmtWhen, parseTs } from "@/lib/format";
import { CommandRefused } from "@/lib/runtime/hooks";
import { useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { toast } from "sonner";

const dayTime = new Intl.DateTimeFormat("it-IT", { weekday: "long", hour: "2-digit", minute: "2-digit" });
const time = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" });

/** "dalle 09:12", "da ieri alle 18:40", "da lunedì alle 16:00". */
function sinceLabel(ts: string): string {
  const ms = parseTs(ts);
  if (ms === null) return "";
  const d = new Date(ms);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return `dalle ${time.format(d)}`;
  const y = new Date();
  y.setDate(y.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return `da ieri alle ${time.format(d)}`;
  return `da ${dayTime.format(d).replace(" ", " alle ")}`;
}

const SEVERITY_DOT: Record<Severity, string> = {
  critical: "bg-halt",
  attention: "bg-warn",
  info: "bg-transparent shadow-[inset_0_0_0_1.5px_var(--fg-subtle)]",
};
const SEVERITY_WORD: Record<Severity, string> = { critical: "Critico", attention: "Da guardare", info: "Informazione" };

/** The counts line in words, zeros left out. */
function countParts(c: BriefingData["counts"]): { n: number; label: string; tone?: "warn" }[] {
  const parts: { n: number; label: string; tone?: "warn" }[] = [
    { n: c.trades, label: c.trades === 1 ? "trade eseguito" : "trade eseguiti" },
    { n: c.orders_pending, label: c.orders_pending === 1 ? "ordine da approvare" : "ordini da approvare", tone: "warn" },
    { n: c.proposals_pending, label: c.proposals_pending === 1 ? "proposta in attesa del PM" : "proposte in attesa del PM" },
    { n: c.proposals_decided, label: c.proposals_decided === 1 ? "proposta decisa" : "proposte decise" },
    { n: c.alerts, label: c.alerts === 1 ? "alert" : "alert", tone: "warn" },
    { n: c.agent_errors, label: c.agent_errors === 1 ? "errore degli agenti" : "errori degli agenti", tone: "warn" },
  ];
  return parts.filter((p) => p.n > 0);
}

function Counts({ b, className }: { b: BriefingData; className?: string }) {
  const parts = countParts(b.counts);
  if (!parts.length) return null;
  return (
    <p className={cn("flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-fg-muted", className)}>
      {parts.map((p) => (
        <span key={p.label}>
          <span className={cn("num font-semibold", p.tone === "warn" ? "text-warn" : "text-fg")}>{p.n}</span> {p.label}
        </span>
      ))}
    </p>
  );
}

function PortfolioChange({ b }: { b: BriefingData }) {
  const p = b.portfolio;
  if (!p) return null;
  const tone = p.change === null ? "" : p.change > 0 ? "bg-up-soft text-up" : p.change < 0 ? "bg-down-soft text-down" : "bg-hover text-fg-muted";
  return (
    <span className="inline-flex items-baseline gap-2 whitespace-nowrap">
      <span className="num text-sm font-semibold text-fg">{fmtMoney(p.value)}</span>
      {p.change !== null && (
        <span className={cn("num rounded-tag px-1.5 text-xs font-medium leading-5", tone)}>
          {fmtMoney(p.change, { sign: true })}
          {p.change_fraction !== null && ` · ${fmtPct(p.change_fraction * 100)}`}
        </span>
      )}
    </span>
  );
}

function ItemRow({ item, onAsk, disabled }: { item: BriefingItem; onAsk: (i: BriefingItem) => void; disabled: boolean }) {
  return (
    <li className="group/item flex items-start gap-3 rounded-item px-2 py-1.5 transition-colors hover:bg-hover">
      <span className={cn("mt-[7px] size-2 shrink-0 rounded-full", SEVERITY_DOT[item.severity])} role="img" aria-label={SEVERITY_WORD[item.severity]} />
      <time className="num mt-px w-11 shrink-0 text-2xs leading-5 text-fg-subtle" dateTime={item.ts}>
        {fmtWhen(item.ts)}
      </time>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] leading-5 text-fg">{item.title}</p>
        {item.detail && <p className="text-xs leading-[1.1rem] text-fg-muted">{item.detail}</p>}
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onAsk(item)}
        className="inline-flex h-6 shrink-0 items-center gap-1 rounded-item px-1.5 text-2xs text-fg-subtle opacity-0 transition-[opacity,background-color,color] hover:bg-selected hover:text-fg focus-visible:opacity-100 group-hover/item:opacity-100 disabled:pointer-events-none [@media(pointer:coarse)]:opacity-100"
        aria-label={`Chiedi al Bridge: ${item.title}`}
        data-action="ask-bridge"
      >
        <MessageSquareReply className="size-3.5" /> Chiedi al Bridge
      </button>
    </li>
  );
}

function useMarkSeen() {
  const { client } = useRuntime();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ts: string) => {
      const res = await client.command("mark_briefing_seen", { ts });
      if (!res.ok) throw new CommandRefused(res.reasons);
    },
    onError: (err) => toast.error("Briefing non segnato come letto", { description: err instanceof CommandRefused ? err.reasons.join(" · ") : err.message }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["bridge", "briefing"] }),
  });
}

/**
 * The morning-report masthead: what happened since the last visit, the Bridge's summary, every item askable.
 * `full` on a new conversation; `compact` (one row that opens in place) while a conversation is active.
 */
export function Briefing({ mode, onAsked }: { mode: "full" | "compact"; onAsked?: () => void }) {
  const q = useBriefing();
  const down = useRuntimeDown();
  const { send, availability } = useBridge();
  const { writable } = useShell();
  const seen = useMarkSeen();
  const [open, setOpen] = useState(false);
  const [all, setAll] = useState(false);

  const ask = (item: BriefingItem) => {
    void send(`Spiegami questa voce del briefing: «${item.title}»${item.detail ? ` (${item.detail})` : ""}`, {
      conversationId: mode === "compact" ? undefined : null,
      context: { page: "assistente", ticker: item.ticker, ref: item.ref ?? { type: "briefing_item", id: item.id } },
    });
    onAsked?.();
  };
  const askDisabled = !writable || availability !== "ready";

  if (q.isPending && down) {
    return <p className={cn("px-5 text-xs text-fg-subtle", mode === "full" ? "pb-4 pt-5" : "py-2.5")}>Briefing non disponibile: Runtime irraggiungibile.</p>;
  }
  if (q.isPending) {
    return (
      <div className={cn("px-5", mode === "full" ? "space-y-2.5 pb-4 pt-5" : "py-2.5")} aria-busy aria-label="Caricamento del briefing">
        <span className="block h-3 w-40 animate-pulse rounded-tag bg-hover" />
        {mode === "full" && (
          <>
            <span className="block h-4 w-4/5 animate-pulse rounded-tag bg-hover" />
            <span className="block h-4 w-3/5 animate-pulse rounded-tag bg-hover" />
          </>
        )}
      </div>
    );
  }
  if (q.isError) {
    return <p className="px-5 py-2.5 text-xs text-warn">Briefing non disponibile: {q.error.message}</p>;
  }
  if (q.data.state !== "ok") {
    return (
      <p data-region="briefing" className="px-5 py-2.5 text-xs text-fg-subtle">
        Briefing non disponibile: il Runtime non espone ancora{" "}
        <code className="font-mono text-2xs text-fg-muted">{q.data.state === "unavailable" ? q.data.endpoint : "GET /v1/read/briefing"}</code>.
      </p>
    );
  }

  const b = q.data.data;
  const quiet = b.items.length === 0;
  const markSeen = (
    <button
      type="button"
      disabled={!writable || seen.isPending || quiet}
      onClick={() => seen.mutate(b.generated_ts || new Date().toISOString())}
      className="inline-flex h-6 shrink-0 items-center gap-1 rounded-item px-1.5 text-2xs text-fg-subtle transition-colors hover:bg-hover hover:text-fg disabled:pointer-events-none disabled:opacity-50"
      data-action="mark-seen"
    >
      <Check className="size-3.5" /> Segna come letto
    </button>
  );

  // Nothing new: one quiet line, whatever the mode.
  if (quiet) {
    return (
      <div data-region="briefing" className="flex items-center gap-3 px-5 py-2.5 text-xs text-fg-subtle">
        <span className="size-2 shrink-0 rounded-full shadow-[inset_0_0_0_1.5px_var(--fg-subtle)]" aria-hidden />
        <span className="min-w-0 flex-1 truncate">
          Niente di nuovo {sinceLabel(b.since)}.{b.summary_text && <span className="text-fg-muted"> {b.summary_text}</span>}
        </span>
        <PortfolioChange b={b} />
      </div>
    );
  }

  const items = all ? b.items : b.items.slice(0, mode === "full" ? 6 : 8);
  const list = (
    <>
      <ul className="mt-2 -mx-2 space-y-px" aria-label="Voci del briefing">
        {items.map((i) => (
          <ItemRow key={i.id} item={i} onAsk={ask} disabled={askDisabled} />
        ))}
      </ul>
      {b.items.length > items.length && (
        <button type="button" onClick={() => setAll(true)} className="mt-1 inline-flex h-6 items-center rounded-item px-1.5 text-2xs text-fg-subtle hover:bg-hover hover:text-fg">
          Mostra tutte le {b.items.length} voci
        </button>
      )}
    </>
  );

  if (mode === "compact") {
    return (
      <div data-region="briefing" className="shrink-0">
        <div className="flex items-center gap-2 px-3 py-1.5">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="flex min-w-0 flex-1 items-center gap-2.5 rounded-item px-2 py-1 text-left transition-colors hover:bg-hover"
          >
            <span className={cn("size-2 shrink-0 rounded-full", b.items.some((i) => i.severity === "critical") ? "bg-halt" : b.items.some((i) => i.severity === "attention") ? "bg-warn" : "bg-fg-subtle")} aria-hidden />
            <span className="shrink-0 text-xs font-semibold text-fg">Briefing</span>
            <span className="shrink-0 text-2xs text-fg-subtle">{sinceLabel(b.since)}</span>
            <span className={cn("min-w-0 flex-1 truncate text-xs text-fg-muted transition-opacity duration-150", open && "opacity-0")} aria-hidden={open}>
              {b.summary_text ?? countParts(b.counts).map((p) => `${p.n} ${p.label}`).join(" · ")}
            </span>
            <ChevronDown className={cn("size-3.5 shrink-0 text-fg-subtle transition-transform duration-200", open && "rotate-180")} aria-hidden />
          </button>
        </div>
        <div className="expand" data-open={open} inert={!open}>
          <div>
            <div className="max-h-[min(50vh,440px)] overflow-y-auto px-5 pb-3">
              {b.summary_text && <p className="max-w-[72ch] text-pretty text-sm leading-[1.35rem] text-fg">{b.summary_text}</p>}
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
                <PortfolioChange b={b} />
                <Counts b={b} />
                <span className="ml-auto">{markSeen}</span>
              </div>
              {list}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <header data-region="briefing" aria-label="Briefing" className="shrink-0 px-5 pb-4 pt-5">
      <div className="flex items-center gap-3">
        <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">Briefing</h2>
        <span className="text-xs text-fg-subtle">
          Cosa è successo {sinceLabel(b.since)}
          {b.summary_ts && <> · sintesi delle {time.format(new Date(parseTs(b.summary_ts) ?? 0))}</>}
        </span>
        <span className="ml-auto">{markSeen}</span>
      </div>
      {b.summary_text ? (
        <p className="mt-2 max-w-[68ch] text-pretty text-[15px] leading-6 text-fg">{b.summary_text}</p>
      ) : (
        <p className="mt-2 text-xs text-fg-subtle">Il Bridge non ha scritto una sintesi (budget del Bridge esaurito o turno non ancora fatto): le voci qui sotto sono complete.</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5">
        <PortfolioChange b={b} />
        <Counts b={b} />
      </div>
      {list}
    </header>
  );
}
