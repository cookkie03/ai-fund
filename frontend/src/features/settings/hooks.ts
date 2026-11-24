import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useRuntime } from "@/lib/runtime/provider";
import { fetchAgentConfigs, fetchBackups, fetchPrompt, fetchPromptHistory, fetchRuntimeHealth, fetchSecrets, fetchSettings, fetchSettingsHistory } from "./api";

// Query keys start with ["cfg", kind] so the SSE invalidation map (lib/runtime/provider.tsx) can target them.
// The secrets read holds only status fields; key values never enter any query or mutation.

export function useSettings() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["cfg", "settings", target.id], queryFn: () => fetchSettings(client), refetchInterval: 120_000 });
}

export function useSettingsHistory() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["cfg", "settings", target.id, "history"], queryFn: () => fetchSettingsHistory(client), refetchInterval: 300_000 });
}

export function useAgentConfigs() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["cfg", "agents", target.id], queryFn: () => fetchAgentConfigs(client), refetchInterval: 60_000 });
}

export function usePrompt(agent: string | null) {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["cfg", "prompt", target.id, agent], queryFn: () => fetchPrompt(client, agent!), enabled: !!agent, staleTime: 30_000 });
}

export function usePromptHistory(agent: string | null) {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["cfg", "prompt", target.id, agent, "history"], queryFn: () => fetchPromptHistory(client, agent!), enabled: !!agent });
}

export function useSecrets() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["cfg", "secrets", target.id], queryFn: () => fetchSecrets(client), refetchInterval: 120_000 });
}

export function useRuntimeHealth() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["cfg", "health", target.id], queryFn: () => fetchRuntimeHealth(client), refetchInterval: 30_000 });
}

export function useBackups() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["cfg", "backups", target.id], queryFn: () => fetchBackups(client), refetchInterval: 300_000 });
}

/** Refetch Configurazioni reads after a command; the SSE events do the same when the backend emits them. */
export function useRefreshCfg() {
  const qc = useQueryClient();
  return useCallback((...kinds: string[]) => {
    for (const k of kinds) qc.invalidateQueries({ queryKey: ["cfg", k] });
  }, [qc]);
}
