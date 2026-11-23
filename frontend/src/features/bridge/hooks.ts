import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useRuntime } from "@/lib/runtime/provider";
import { fetchActions, fetchBriefing, fetchConversation, fetchConversations } from "./api";

// Keys start with ["bridge", kind] so the SSE map (bridge.*, briefing.updated) can target them by prefix.

export function useConversations(params: { q?: string; archived?: boolean } = {}) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["bridge", "conversations", target.id, params.q ?? "", params.archived ?? false],
    queryFn: () => fetchConversations(client, params),
    placeholderData: keepPreviousData,
    // Events keep it current; the interval covers a dropped stream.
    refetchInterval: 30_000,
  });
}

export function useConversation(id: number | null) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["bridge", "conversation", target.id, id],
    queryFn: () => fetchConversation(client, id!),
    enabled: id !== null,
    refetchInterval: 30_000,
  });
}

export function useBridgeActions(status?: string) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["bridge", "actions", target.id, status ?? ""],
    queryFn: () => fetchActions(client, status),
    refetchInterval: 30_000,
  });
}

export function useBriefing() {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["bridge", "briefing", target.id],
    queryFn: () => fetchBriefing(client),
    refetchInterval: 120_000,
  });
}

/** The Runtime stopped answering (not merely still booting): reads will not arrive, so say so instead of a skeleton. */
export function useRuntimeDown(): boolean {
  const { connection } = useRuntime();
  return !connection.reachable && !connection.booting;
}
