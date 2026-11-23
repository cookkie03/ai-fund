import { useQuery } from "@tanstack/react-query";
import { parseTs } from "@/lib/format";
import { useRuntime } from "@/lib/runtime/provider";
import type { Message } from "@/lib/runtime/types";
import { fetchAgents, fetchChat, fetchToolCalls, fetchTopics, fetchUsage, recentCycleMessages } from "./api";

// Query keys start with ["office", kind] so the SSE invalidation map can target them by prefix.

export function useOfficeAgents() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["office", "agents", target.id], queryFn: () => fetchAgents(client), refetchInterval: 30_000 });
}

export function useChatTopics(agent: string | null) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["office", "topics", target.id, agent],
    queryFn: () => fetchTopics(client, agent!),
    enabled: !!agent,
    refetchInterval: 60_000,
  });
}

export function useChat(agent: string | null, topic: string | null) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["office", "chat", target.id, agent, topic],
    queryFn: () => fetchChat(client, agent!, topic!),
    enabled: !!agent && !!topic,
    refetchInterval: 60_000,
  });
}

export function useToolCalls(agent: string | null) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["office", "tools", target.id, agent],
    queryFn: () => fetchToolCalls(client, agent!),
    enabled: !!agent,
    // The stream invalidates on tool.* events; the interval only covers a dropped stream.
    refetchInterval: 30_000,
  });
}

export type UsagePeriod = "today" | "7d" | "30d";

export const PERIOD_LABEL: Record<UsagePeriod, string> = { today: "Oggi", "7d": "7 giorni", "30d": "30 giorni" };

function periodStart(period: UsagePeriod, now = new Date()): string {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  if (period === "7d") d.setDate(d.getDate() - 6);
  if (period === "30d") d.setDate(d.getDate() - 29);
  return d.toISOString();
}

export function useUsage(agent: string | null, period: UsagePeriod) {
  const { client, target } = useRuntime();
  // The day boundary is fixed per render so the key is stable within a day.
  const from = periodStart(period);
  return useQuery({
    queryKey: ["office", "usage", target.id, agent, from],
    queryFn: () => fetchUsage(client, { agent: agent ?? undefined, from }),
    refetchInterval: 60_000,
  });
}

export type RecentMessage = Message & { ticker: string; cycleStatus: string };

/** The office's latest messages across recent cycles, newest first: what the agents are saying right now. */
export function useRecentMessages(limit = 14) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["office", "chat", target.id, "recent", limit],
    queryFn: async () => {
      const cycles = await recentCycleMessages(client, 10);
      return cycles
        .flatMap((c) => c.messages.map<RecentMessage>((m) => ({ ...m, ticker: c.ticker, cycleStatus: c.status })))
        .sort((a, b) => (parseTs(b.ts) ?? 0) - (parseTs(a.ts) ?? 0) || b.id - a.id)
        .slice(0, limit);
    },
    refetchInterval: 60_000,
  });
}
