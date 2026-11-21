import { Activity, ChevronDown, Server, Unplug } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { fmtAge, fmtDateTime } from "@/lib/format";
import { STALE_AFTER_MS, useNow, useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";

export type Freshness = "live" | "stale" | "down" | "booting";

/** One rule for the whole shell: live stream = live; stream lost = stale with age; no Runtime = down. */
export function useFreshness(): { state: Freshness; age: number | null } {
  const { connection } = useRuntime();
  const now = useNow(1000);
  const age = connection.lastSyncAt ? now - connection.lastSyncAt : null;
  if (connection.booting) return { state: "booting", age };
  if (!connection.reachable) return { state: "down", age };
  // The Runtime flushes SSE headers on its first event or 15 s ping: a first connection still pending is not stale data.
  if (connection.stream === "connecting" && (age === null || age <= STALE_AFTER_MS)) return { state: "booting", age };
  if (connection.stream !== "open" || (age !== null && age > STALE_AFTER_MS)) return { state: "stale", age };
  return { state: "live", age };
}

const DOT: Record<Freshness, string> = {
  live: "bg-up",
  stale: "bg-warn",
  down: "bg-down",
  booting: "bg-fg-faint",
};

export function StatusDot({ state, className }: { state: Freshness; className?: string }) {
  return (
    <span
      className={cn("inline-block size-2 shrink-0 rounded-full", DOT[state], className)}
      style={state === "stale" ? { animation: "status-pulse 1.6s ease-in-out infinite" } : undefined}
      aria-hidden
    />
  );
}

export function RuntimeStatus({ compact = false }: { compact?: boolean }) {
  const { health, connection } = useRuntime();
  const { state, age } = useFreshness();
  const now = useNow(1000);

  const label =
    state === "live" ? "Live" : state === "stale" ? `Dati vecchi · ${fmtAge(connection.lastSyncAt, now)}` : state === "down" ? "Runtime irraggiungibile" : "Connessione…";
  const broker = !health ? "—" : !health.broker_configured ? "Broker non configurato" : health.broker_stream_connected ? "Stream broker connesso" : "Stream broker disconnesso";
  const brokerTone = health?.broker_configured && health.broker_stream_connected ? "text-up" : health?.broker_configured ? "text-warn" : "text-fg-subtle";

  return (
    <Popover>
      <PopoverTrigger
        className={cn(
          "inline-flex h-7 items-center gap-2 rounded-control px-2 text-xs transition-colors hover:bg-hover",
          state === "down" ? "text-down" : state === "stale" ? "text-warn" : "text-fg-muted",
        )}
        aria-label={`Stato del Runtime: ${label}. ${broker}`}
      >
        <StatusDot state={state} />
        {!compact && <span className="num whitespace-nowrap">{label}</span>}
        {!compact && health && (
          <span className={cn("hidden items-center gap-1 xl:inline-flex", brokerTone)}>
            <span className="text-fg-faint">·</span>
            {health.broker_configured && health.broker_stream_connected ? <Activity className="size-3.5" /> : <Unplug className="size-3.5" />}
            <span className="whitespace-nowrap">{health.broker_configured ? (health.broker_stream_connected ? "Broker" : "Broker offline") : "Broker n/c"}</span>
          </span>
        )}
        <ChevronDown className="size-3 text-fg-faint" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 border-line-strong bg-raised p-0 text-xs">
        <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
          <Server className="size-4 text-fg-subtle" />
          <span className="font-medium text-fg">Runtime {health?.account_label ?? ""}</span>
          <span className="ml-auto text-fg-subtle">v{health?.runtime_version ?? "—"}</span>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 px-3 py-2.5">
          <dt className="text-fg-subtle">Runtime</dt>
          <dd className={cn("text-right", state === "down" ? "text-down" : "text-fg")}>{state === "down" ? "Irraggiungibile" : "Raggiungibile"}</dd>
          <dt className="text-fg-subtle">Stream eventi</dt>
          <dd className={cn("text-right", connection.stream === "open" ? "text-fg" : "text-warn")}>
            {connection.stream === "open" ? "Connesso" : connection.stream === "reconnecting" ? "Riconnessione…" : connection.stream === "connecting" ? "Connessione…" : "Chiuso"}
          </dd>
          <dt className="text-fg-subtle">Ultimo aggiornamento</dt>
          <dd className="num text-right text-fg">{connection.lastSyncAt ? `${fmtAge(connection.lastSyncAt, now)} fa` : "—"}</dd>
          <dt className="text-fg-subtle">Ultimo evento</dt>
          <dd className="num text-right text-fg">{connection.lastEventAt ? `${fmtAge(connection.lastEventAt, now)} fa` : health ? `#${health.last_event_id}` : "—"}</dd>
          <dt className="text-fg-subtle">Broker</dt>
          <dd className={cn("text-right", brokerTone)}>{broker}</dd>
          <dt className="text-fg-subtle">Prossimo task</dt>
          <dd className="num text-right text-fg">{health?.next_scheduler_due_ts ? fmtDateTime(health.next_scheduler_due_ts) : "Nessuno"}</dd>
          <dt className="text-fg-subtle">Database</dt>
          <dd className="num text-right text-fg">{health ? `${(health.db_size_bytes / 1048576).toFixed(1).replace(".", ",")} MB` : "—"}</dd>
        </dl>
        {age !== null && state === "stale" && (
          <p className="border-t border-line px-3 py-2 text-warn">Lo stream eventi è interrotto: i valori a schermo possono non essere aggiornati.</p>
        )}
      </PopoverContent>
    </Popover>
  );
}
