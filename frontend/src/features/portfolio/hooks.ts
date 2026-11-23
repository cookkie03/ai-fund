import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RuntimeError } from "@/lib/runtime/client";
import { useRuntime } from "@/lib/runtime/provider";
import {
  closePosition,
  fetchAllocation,
  fetchAttribution,
  fetchBenchmarkBars,
  fetchEquity,
  fetchPerformance,
  fetchPositions,
  fetchRiskHistory,
  fetchRiskLimits,
  fetchSummary,
  fetchTrades,
  isCommandMissing,
  modifyExit,
  updateRiskLimits,
  type CommandOutcome,
} from "./api";
import type { ClosePositionPayload, ModifyExitPayload, Period, UpdateRiskLimitsPayload } from "./types";

// Query keys start with ["pf", kind] so the SSE invalidation map (lib/runtime/provider.tsx) can target them.

export function useSummary() {
  const { client, target, health } = useRuntime();
  const halted = health?.halted ?? false;
  return useQuery({ queryKey: ["pf", "summary", target.id, halted], queryFn: () => fetchSummary(client, halted), refetchInterval: 30_000 });
}

export function usePositions() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["pf", "positions", target.id], queryFn: () => fetchPositions(client), refetchInterval: 30_000 });
}

export function useAllocation() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["pf", "allocation", target.id], queryFn: () => fetchAllocation(client), refetchInterval: 60_000 });
}

export function useEquityCurve() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["pf", "equity", target.id], queryFn: () => fetchEquity(client), refetchInterval: 60_000 });
}

export function useBenchmark(enabled: boolean) {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["pf", "benchmark", target.id, "SPY"], queryFn: () => fetchBenchmarkBars(client, "SPY"), enabled, staleTime: 5 * 60_000 });
}

export function usePerformance(period: Period) {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["pf", "performance", target.id, period], queryFn: () => fetchPerformance(client, period), placeholderData: keepPreviousData, refetchInterval: 120_000 });
}

export function useAttribution(period: Period) {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["pf", "attribution", target.id, period], queryFn: () => fetchAttribution(client, period), placeholderData: keepPreviousData, refetchInterval: 120_000 });
}

export function usePortfolioTrades() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["pf", "trades", target.id], queryFn: () => fetchTrades(client), refetchInterval: 60_000 });
}

export function useRiskLimits() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["pf", "risk", target.id], queryFn: () => fetchRiskLimits(client), refetchInterval: 60_000 });
}

export function useRiskHistory() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["pf", "risk", target.id, "history"], queryFn: () => fetchRiskHistory(client), refetchInterval: 120_000 });
}

/** Why a capital command failed in a way the dialog should say in words. */
export function commandErrorText(err: unknown, name: string): string {
  if (isCommandMissing(err)) return `Il Runtime non espone ancora il comando ${name}.`;
  if (err instanceof RuntimeError && err.unreachable) return "Runtime irraggiungibile: il comando non è stato inviato.";
  return err instanceof Error ? err.message : String(err);
}

const INVALIDATE = [["pf"], ["portfolio"], ["orders"], ["trades"], ["inbox"], ["equity"]];

function useCapitalCommand<P extends { dry_run?: boolean }, T>(name: string, send: (p: P) => Promise<CommandOutcome<T>>, success: (p: P) => string) {
  const qc = useQueryClient();
  return useMutation<CommandOutcome<T>, Error, P>({
    mutationFn: send,
    onSuccess: (res, p) => {
      if (p.dry_run) return;
      if (res.ok) toast.success(success(p));
      for (const key of INVALIDATE) qc.invalidateQueries({ queryKey: key });
    },
    onError: (err, p) => {
      if (!p.dry_run) toast.error(`Comando ${name} non riuscito`, { description: commandErrorText(err, name) });
    },
  });
}

export function useClosePosition() {
  const { client } = useRuntime();
  return useCapitalCommand<ClosePositionPayload, Awaited<ReturnType<typeof closePosition>> extends CommandOutcome<infer T> ? T : never>(
    "close_position",
    (p) => closePosition(client, p),
    (p) => (p.qty === null ? `Chiusura di ${p.ticker} inviata` : `Riduzione di ${p.ticker} inviata`),
  );
}

export function useModifyExit() {
  const { client } = useRuntime();
  return useCapitalCommand<ModifyExitPayload, Awaited<ReturnType<typeof modifyExit>> extends CommandOutcome<infer T> ? T : never>(
    "modify_exit",
    (p) => modifyExit(client, p),
    (p) => `Uscite di ${p.ticker} aggiornate`,
  );
}

export function useUpdateRiskLimits() {
  const { client } = useRuntime();
  return useCapitalCommand<UpdateRiskLimitsPayload & { dry_run?: boolean }, Record<string, unknown>>("update_risk_limits", (p) => updateRiskLimits(client, p), () => "Vincoli di rischio aggiornati");
}
