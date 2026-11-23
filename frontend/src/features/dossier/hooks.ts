import { useQuery } from "@tanstack/react-query";
import { useRuntime } from "@/lib/runtime/provider";
import { fetchDossier, fetchDossierHistory, fetchDossiers, fetchProposals } from "./api";

// Keys start with the read's name so the SSE map (dossier.updated, proposal.*) can target them by prefix.

export function useDossier(ticker: string | null) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["dossier", target.id, ticker],
    queryFn: () => fetchDossier(client, ticker!),
    enabled: !!ticker,
    refetchInterval: 60_000,
  });
}

export function useDossierHistory(ticker: string | null) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["dossier_history", target.id, ticker],
    queryFn: () => fetchDossierHistory(client, ticker!),
    enabled: !!ticker,
    refetchInterval: 120_000,
  });
}

export function useProposals(params: { status?: string; ticker?: string } = {}) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["proposals", target.id, params.status ?? "", params.ticker ?? ""],
    queryFn: () => fetchProposals(client, params),
    refetchInterval: 30_000,
  });
}

export function useDossiers() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["dossiers", target.id], queryFn: () => fetchDossiers(client), refetchInterval: 60_000 });
}
