import { AlertTriangle, Archive, Check, ChevronRight, Copy, Loader2, PanelRightClose, Wrench } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { IconButton } from "@/components/tile";
import { Button } from "@/components/ui/button";
import { useToolCalls } from "@/features/office/hooks";
import type { ToolCall } from "@/features/office/types";
import { author } from "@/lib/authors";
import { fmtAge, fmtDateTime, fmtWhen } from "@/lib/format";
import { useNow, useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { PANEL_SHORTCUT } from "@/shell/shell-state";
import { useFreshness } from "@/shell/status";
import { onRadioKeys } from "./parts";

type Filter = "all" | "errors";

const sec = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

function fmtDuration(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${sec.format(ms / 1000)} s`;
  return `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`;
}

/** The two or three arguments that tell calls apart, as `key value`. */
function argSummary(params: Record<string, unknown> | null): string {
  if (!params) return "";
  return Object.entries(params)
    .filter(([, v]) => v !== null && v !== undefined && (typeof v !== "object" || Array.isArray(v)))
    .slice(0, 3)
    .map(([k, v]) => `${k} ${Array.isArray(v) ? v.join(",") : String(v)}`)
    .join(" · ");
}

function pretty(v: unknown): string {
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function Payload({ label, value, compacted, compactedAt }: { label: string; value: unknown; compacted: boolean; compactedAt: string | null }) {
  const [copied, setCopied] = useState(false);
  const text = pretty(value);
  const empty = value === null || value === undefined || text === "{}" || text === "";
  return (
    <section className="mt-2 first:mt-0">
      <div className="mb-1 flex h-5 items-center gap-2">
        <h4 className="text-2xs text-fg-subtle">{label}</h4>
        {!compacted && !empty && (
          <Button
            type="button"
            variant="ghost"
            size="xs"
            onClick={() => {
              void navigator.clipboard?.writeText(text).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1200);
              });
            }}
            className="ml-auto h-5 gap-1 rounded-tag px-1 text-2xs text-fg-subtle"
          >
            {copied ? <Check className="size-3" /> : <Copy className="size-3" />} {copied ? "Copiato" : "Copia"}
          </Button>
        )}
      </div>
      {compacted ? (
        <p className="flex items-start gap-1.5 rounded-item border border-border/50 bg-muted/50 px-2.5 py-2 text-xs leading-4 text-fg-muted">
          <Archive className="mt-px size-3.5 shrink-0 text-fg-subtle" aria-hidden />
          <span>Compattato dalla retention{compactedAt ? ` il ${fmtDateTime(compactedAt)}` : ""}: il contenuto completo non è più nel database.</span>
        </p>
      ) : empty ? (
        <p className="px-0.5 text-xs text-fg-subtle">Vuoto</p>
      ) : (
        <pre className="max-h-64 overflow-auto rounded-item border border-border/50 bg-muted/50 px-2.5 py-2 font-mono text-[11px] leading-4 text-fg-muted">{text}</pre>
      )}
    </section>
  );
}

function StatusIcon({ call }: { call: ToolCall }) {
  if (call.status === "running") return <Loader2 className="size-3.5 animate-spin text-fg-muted" aria-label="In corso" />;
  if (call.status === "error") return <AlertTriangle className="size-3.5 text-warn" aria-label="Errore" />;
  return <Check className="size-3.5 text-fg-subtle" aria-label="Riuscita" />;
}

function ToolBlock({ call, fresh }: { call: ToolCall; fresh: boolean }) {
  const [open, setOpen] = useState(false);
  const running = call.status === "running";
  // Only a running call needs a ticking clock; finished ones refresh their time label once a minute.
  const now = useNow(running ? 1000 : 60_000);
  const summary = argSummary(call.params);
  const elapsed = running ? now - (Date.parse(call.ts) || now) : call.duration_ms;
  const id = `tool-${call.id}`;

  return (
    <li className={cn("rounded-item transition-colors duration-150", open ? "bg-hover" : "hover:bg-hover", fresh && "row-arrive")}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full min-w-0 items-start gap-2 rounded-item px-2.5 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
      >
        <span className="mt-0.5 grid size-4 shrink-0 place-items-center">
          <StatusIcon call={call} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 items-baseline gap-2">
            <span className={cn("truncate font-mono text-xs", call.status === "error" ? "text-warn" : "text-fg")}>{call.tool}</span>
            <span className={cn("num ml-auto shrink-0 text-2xs", running ? "text-fg-muted" : "text-fg-subtle")}>
              {running ? `${fmtDuration(elapsed)} · in corso` : fmtDuration(elapsed)}
            </span>
          </span>
          <span className="mt-0.5 flex min-w-0 items-baseline gap-2 text-2xs text-fg-subtle">
            <span className="min-w-0 truncate">{call.status === "error" && call.error ? call.error : summary || "senza argomenti"}</span>
            <span className="num ml-auto shrink-0">{fmtWhen(call.ts, now)}</span>
          </span>
        </span>
        <ChevronRight className={cn("mt-0.5 size-3.5 shrink-0 text-fg-subtle transition-transform duration-200", open && "rotate-90")} aria-hidden />
      </button>
      <div id={id} className="expand" data-open={open} role="region" aria-label={`Dettagli di ${call.tool}`}>
        <div>
          {open && (
            <div className="px-2.5 pb-2.5 pl-8">
              {(call.topic || call.cycle_id !== null) && (
                <p className="mb-2 text-2xs text-fg-subtle">
                  {call.topic && <>chat <span className="text-fg-muted">{call.topic}</span></>}
                  {call.topic && call.cycle_id !== null && " · "}
                  {call.cycle_id !== null && <>ciclo <span className="num text-fg-muted">#{call.cycle_id}</span></>}
                </p>
              )}
              <Payload label="Input" value={call.params} compacted={call.compacted.params} compactedAt={call.compacted.at} />
              {call.status === "error" && call.error && (
                <section className="mt-2">
                  <h4 className="mb-1 text-2xs text-fg-subtle">Errore</h4>
                  <p className="rounded-item bg-warn-soft px-2.5 py-2 font-mono text-[11px] leading-4 text-fg">{call.error}</p>
                </section>
              )}
              {running ? (
                <p className="mt-2 text-xs text-fg-subtle">Output in arrivo: la chiamata è ancora in corso.</p>
              ) : (
                <Payload label="Output" value={call.result} compacted={call.compacted.result} compactedAt={call.compacted.at} />
              )}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function StreamState() {
  const { state } = useFreshness();
  const { connection } = useRuntime();
  const now = useNow(1000);
  if (state === "live") {
    return (
      <span className="inline-flex items-center gap-1.5 text-2xs text-fg-subtle">
        <span className="size-1.5 rounded-full bg-fg-muted" aria-hidden /> Dal vivo
      </span>
    );
  }
  if (state === "booting") return <span className="text-2xs text-fg-subtle">Connessione…</span>;
  return (
    <span className="num inline-flex items-center gap-1.5 text-2xs text-warn" title="Lo stream eventi è interrotto: le nuove chiamate arrivano solo con l'aggiornamento periodico.">
      <span className="size-1.5 rounded-full bg-warn" style={{ animation: "status-pulse 1.6s ease-in-out infinite" }} aria-hidden />
      Fermo da {fmtAge(connection.lastSyncAt, now)}
    </span>
  );
}

/** Live stream of one agent's tool calls, newest first. Each block opens in place to its input and output. */
export function ToolStream({ agent, onHide, className, style }: { agent: string; onHide?: () => void; className?: string; style?: CSSProperties }) {
  const q = useToolCalls(agent);
  const [filter, setFilter] = useState<Filter>("all");
  const seen = useRef<Set<number> | null>(null);
  const calls = q.data?.source === "runtime" ? q.data.data : [];
  const sorted = [...calls].sort((a, b) => (a.status === "running" ? -1 : 0) - (b.status === "running" ? -1 : 0) || (Date.parse(b.ts) || 0) - (Date.parse(a.ts) || 0));
  const errors = calls.filter((c) => c.status === "error").length;
  const shown = filter === "errors" ? sorted.filter((c) => c.status === "error") : sorted;

  // Rows that arrive after the first load slide in; the first paint stays still.
  const fresh = new Set<number>();
  if (seen.current) for (const c of calls) if (!seen.current.has(c.id)) fresh.add(c.id);
  useEffect(() => {
    if (q.data?.source === "runtime") seen.current = new Set(q.data.data.map((c) => c.id));
  }, [q.data]);
  useEffect(() => {
    seen.current = null;
    setFilter("all");
  }, [agent]);

  return (
    <aside aria-label={`Tool di ${author(agent).name}`} className={cn("flex min-h-0 flex-col bg-ground", className)} style={style}>
      <header className="flex h-11 shrink-0 items-center gap-2 pl-4 pr-2">
        <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">Tool</h2>
        {calls.length > 0 && <span className="num rounded-tag bg-hover px-1.5 text-[10px] leading-4 text-fg-subtle">{calls.length}</span>}
        <span className="ml-1">
          <StreamState />
        </span>
        <div className="ml-auto flex items-center gap-0.5">
          {onHide && <IconButton icon={PanelRightClose} label="Nascondi i tool" shortcut={PANEL_SHORTCUT.right} onClick={onHide} />}
        </div>
      </header>

      {q.data?.source === "runtime" && calls.length > 0 && (
        <div className="px-3 pb-2">
          <div role="radiogroup" aria-label="Filtro" className="seg" onKeyDown={onRadioKeys}>
            <button type="button" role="radio" aria-checked={filter === "all"} tabIndex={filter === "all" ? 0 : -1} onClick={() => setFilter("all")} className="seg-item">
              Tutte
            </button>
            <button type="button" role="radio" aria-checked={filter === "errors"} tabIndex={filter === "errors" ? 0 : -1} onClick={() => setFilter("errors")} className="seg-item" disabled={errors === 0}>
              Errori
              {errors > 0 && <span className="num rounded-tag bg-warn-soft px-1 text-[10px] leading-4 text-warn">{errors}</span>}
            </button>
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {q.isPending ? (
          <ul className="space-y-1 px-1" aria-busy aria-label="Caricamento dei tool">
            {[0, 1, 2, 3, 4].map((i) => (
              <li key={i} className="flex gap-2 px-1.5 py-2">
                <span className="size-4 animate-pulse rounded-tag bg-hover" />
                <span className="flex-1 space-y-1.5">
                  <span className="block h-3 w-2/3 animate-pulse rounded-tag bg-hover" />
                  <span className="block h-2.5 w-1/2 animate-pulse rounded-tag bg-hover" />
                </span>
              </li>
            ))}
          </ul>
        ) : q.isError ? (
          <p className="px-2.5 py-3 text-xs text-down">Lettura dei tool non riuscita: {q.error.message}</p>
        ) : q.data.source === "unavailable" ? (
          <div className="px-2.5 py-6 text-center">
            <Wrench className="mx-auto size-5 text-fg-subtle" strokeWidth={1.5} aria-hidden />
            <p className="mx-auto mt-3 max-w-[30ch] text-xs leading-relaxed text-fg-muted">{q.data.note}</p>
            <p className="mx-auto mt-1.5 max-w-[34ch] text-2xs leading-4 text-fg-subtle">Le chiamate compariranno qui dal vivo quando arrivano l'endpoint tool_calls e l'evento tool.called.</p>
          </div>
        ) : shown.length === 0 ? (
          <p className="px-2.5 py-6 text-center text-xs text-fg-subtle">
            {filter === "errors" ? "Nessuna chiamata fallita." : `${author(agent).short} non ha ancora chiamato tool.`}
          </p>
        ) : (
          <ol className="space-y-0.5">
            {shown.map((c) => (
              <ToolBlock key={c.id} call={c} fresh={fresh.has(c.id)} />
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
