import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { RuntimeClient, RuntimeError } from "./client";
import { subscribeEvents, type StreamStatus } from "./sse";
import type { Health, RuntimeEvent } from "./types";

/** One Runtime per broker account. The backend has no registry: the list is frontend config. */
export type RuntimeTarget = { id: string; url: string; label?: string };

function readTargets(): RuntimeTarget[] {
  const raw = import.meta.env.VITE_COCKPIT_RUNTIMES as string | undefined;
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as RuntimeTarget[];
      if (Array.isArray(parsed) && parsed.length) return parsed;
    } catch {
      console.warn("VITE_COCKPIT_RUNTIMES non è JSON valido; uso il Runtime locale");
    }
  }
  return [{ id: "local", url: "" }];
}

const STORAGE_KEY = "cockpit.runtime";

export type Connection = {
  /** Runtime answered the last health check. */
  reachable: boolean;
  /** Health has never loaded yet. */
  booting: boolean;
  stream: StreamStatus;
  /** Epoch ms of the last proof the data is current (health answer or live event). */
  lastSyncAt: number | null;
  /** Epoch ms of the last event received over SSE. */
  lastEventAt: number | null;
};

type Ctx = {
  targets: RuntimeTarget[];
  target: RuntimeTarget;
  selectTarget: (id: string) => void;
  client: RuntimeClient;
  health: Health | undefined;
  connection: Connection;
  /** Subscribe to every live event (after the replay). */
  onEvent: (fn: (e: RuntimeEvent) => void) => () => void;
};

const RuntimeCtx = createContext<Ctx | null>(null);

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (count, err) => !(err instanceof RuntimeError && !err.unreachable && err.status && err.status < 500) && count < 2,
      refetchOnWindowFocus: true,
    },
  },
});

/** Which reads an event makes stale. Keys are query-key prefixes. */
function keysFor(type: string): string[][] {
  if (type.startsWith("order.")) return [["orders"], ["inbox"], ["pf", "trades"]];
  if (type.startsWith("trade.")) return [["trades"], ["orders"], ["portfolio"], ["pf"]];
  if (type === "portfolio.updated") return [["portfolio"], ["equity"], ["pf"]];
  if (type === "position.changed") return [["portfolio"], ["trades"], ["pf"]];
  if (type === "risk_limits.updated") return [["pf", "risk"], ["inbox"]];
  if (type.startsWith("annotation.")) return [["annotations"]];
  if (type === "watchlist.changed") return [["watchlist"]];
  if (type === "halt.changed") return [["health"], ["orders"], ["pf", "summary"]];
  if (type === "inbox.changed") return [["inbox"]];
  if (type === "portfolio.synced") return [["portfolio"], ["equity"], ["pf"]];
  if (type === "message.appended" || type === "chat.message") return [["cycles"], ["ticker_state"], ["office", "chat"], ["office", "topics"], ["office", "agents"]];
  if (type.startsWith("cycle.")) return [["cycles"], ["ticker_state"], ["office", "agents"], ["office", "topics"]];
  if (type.startsWith("task.")) return [["office", "agents"]];
  if (type.startsWith("tool.")) return [["office", "tools"], ["office", "agents"], ["office", "usage"]];
  if (type === "agent.status") return [["office", "agents"]];
  if (type === "dossier.updated") return [["dossier"], ["dossier_history"], ["dossiers"]];
  if (type.startsWith("proposal.")) return [["proposals"], ["dossier"], ["dossiers"], ["dossier_history"], ["office", "agents"]];
  if (type === "data.refreshed") return [["bars"], ["indicators"]];
  return [];
}

function RuntimeSession({ target, targets, selectTarget, children }: { target: RuntimeTarget; targets: RuntimeTarget[]; selectTarget: (id: string) => void; children: ReactNode }) {
  const client = useMemo(() => new RuntimeClient(target.url), [target.url]);
  const qc = useQueryClient();
  const listeners = useRef(new Set<(e: RuntimeEvent) => void>());
  const [stream, setStream] = useState<StreamStatus>("connecting");
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);

  const healthQ = useQuery({
    queryKey: ["health", target.id],
    queryFn: client.health,
    refetchInterval: 10_000,
    retry: false,
  });

  const reachable = healthQ.isSuccess && !healthQ.isError;
  const startAfter = healthQ.data?.last_event_id ?? null;
  const streamStarted = startAfter !== null;

  useEffect(() => {
    if (!streamStarted) return;
    return subscribeEvents({
      url: (after) => client.eventsUrl(after),
      initialAfter: startAfter,
      onStatus: setStream,
      onEvent: (event) => {
        setLastEventAt(Date.now());
        for (const key of keysFor(event.type)) qc.invalidateQueries({ queryKey: key });
        listeners.current.forEach((fn) => fn(event));
      },
    });
    // Reopen only when the account changes; replay covers everything else.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, streamStarted]);

  const onEvent = useCallback((fn: (e: RuntimeEvent) => void) => {
    listeners.current.add(fn);
    return () => listeners.current.delete(fn);
  }, []);

  const healthAt = healthQ.isSuccess ? healthQ.dataUpdatedAt : null;
  const connection: Connection = {
    reachable,
    booting: healthQ.isPending,
    stream,
    lastSyncAt: Math.max(healthAt ?? 0, lastEventAt ?? 0) || null,
    lastEventAt,
  };

  const value: Ctx = { targets, target, selectTarget, client, health: healthQ.data, connection, onEvent };
  return <RuntimeCtx.Provider value={value}>{children}</RuntimeCtx.Provider>;
}

export function RuntimeProvider({ children }: { children: ReactNode }) {
  const targets = useMemo(readTargets, []);
  const [targetId, setTargetId] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved && targets.some((t) => t.id === saved)) return saved;
    } catch {
      /* storage unavailable */
    }
    return targets[0].id;
  });
  const target = targets.find((t) => t.id === targetId) ?? targets[0];

  const selectTarget = useCallback((id: string) => {
    setTargetId(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* storage unavailable */
    }
    queryClient.clear();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <RuntimeSession key={target.id} target={target} targets={targets} selectTarget={selectTarget}>
        {children}
      </RuntimeSession>
    </QueryClientProvider>
  );
}

export function useRuntime(): Ctx {
  const ctx = useContext(RuntimeCtx);
  if (!ctx) throw new Error("useRuntime outside RuntimeProvider");
  return ctx;
}

/** Re-render every `ms` so relative ages stay true. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

export const STALE_AFTER_MS = 30_000;
