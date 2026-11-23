import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RuntimeError } from "./client";
import { useRuntime } from "./provider";
import type { CommandName, CommandPayloads, CommandResult } from "./types";

export function usePortfolio() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["portfolio", target.id], queryFn: client.portfolio, refetchInterval: 60_000 });
}

export function useEquityHistory() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["equity", target.id], queryFn: () => client.equityHistory(), staleTime: 60_000 });
}

export function useOrders() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["orders", target.id], queryFn: () => client.orders(undefined, 200), refetchInterval: 30_000 });
}

export function useTrades() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["trades", target.id], queryFn: () => client.trades({ limit: 200 }), refetchInterval: 60_000 });
}

export function useWatchlist() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["watchlist", target.id], queryFn: client.watchlist });
}

export function useInbox() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["inbox", target.id], queryFn: () => client.inbox(false, 50), refetchInterval: 60_000 });
}

export function useTickerState(ticker: string | null) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["ticker_state", target.id, ticker],
    queryFn: () => client.tickerState(ticker!),
    enabled: !!ticker,
  });
}

export function useCycles(ticker: string | null) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["cycles", target.id, ticker],
    queryFn: () => client.cycles({ ticker: ticker!, limit: 10 }),
    enabled: !!ticker,
  });
}

export function useCycle(id: number | null) {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["cycles", target.id, "detail", id], queryFn: () => client.cycle(id!), enabled: id !== null });
}

export function useBars(ticker: string | null, timeframe: string | null, limit = 600) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["bars", target.id, ticker, timeframe, limit],
    queryFn: () => client.bars(ticker!, timeframe, limit),
    enabled: !!ticker,
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });
}

/** Small bar windows for the watchlist (last price, change, sparkline), one query per ticker. */
export function useWatchBars(tickers: string[]) {
  const { client, target } = useRuntime();
  return useQueries({
    queries: tickers.map((t) => ({
      queryKey: ["bars", target.id, t, "1h", 60],
      queryFn: () => client.bars(t, "1h", 60),
      refetchInterval: 60_000,
      staleTime: 30_000,
    })),
  });
}

export function useIndicators(ticker: string | null, names: string[], timeframe: string | null, limit = 600) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["indicators", target.id, ticker, timeframe, names.join(","), limit],
    queryFn: () => client.indicators(ticker!, names, timeframe, limit),
    enabled: !!ticker && names.length > 0,
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });
}

export function useAnnotations(ticker: string | null) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["annotations", target.id, ticker],
    queryFn: () => client.annotations(ticker!, true),
    enabled: !!ticker,
  });
}

type CommandOpts = {
  /** Toast on success; false keeps it silent. */
  success?: string | false;
  /** Query prefixes to refetch after the command settles. */
  invalidate?: string[][];
  /** False when the caller shows the refusal reasons inline, next to the control that caused them. */
  toastRefusal?: boolean;
};

/**
 * Runs a Runtime command. A domain refusal (`ok: false`) is surfaced with the Runtime's reasons
 * and rejects the mutation, so callers can keep the UI in its previous state.
 */
export function useCommand<N extends CommandName>(name: N, opts: CommandOpts = {}) {
  const { client } = useRuntime();
  const qc = useQueryClient();
  return useMutation<CommandResult, Error, CommandPayloads[N]>({
    mutationFn: async (payload) => {
      const res = await client.command(name, payload);
      if (!res.ok) throw new CommandRefused(res.reasons);
      return res;
    },
    onSuccess: () => {
      if (opts.success) toast.success(opts.success);
    },
    onError: (err) => {
      if (err instanceof CommandRefused) {
        if (opts.toastRefusal === false) return;
        toast.error("Il Runtime ha rifiutato il comando", { description: err.reasons.join(" · ") || "Nessuna ragione indicata" });
      } else if (err instanceof RuntimeError && err.unreachable) {
        toast.error("Runtime irraggiungibile", { description: "Il comando non è stato inviato. Riprova quando torna raggiungibile." });
      } else {
        toast.error("Comando non valido", { description: err.message });
      }
    },
    onSettled: () => {
      for (const key of opts.invalidate ?? []) qc.invalidateQueries({ queryKey: key });
    },
  });
}

export class CommandRefused extends Error {
  constructor(readonly reasons: string[]) {
    super(reasons.join("; ") || "Comando rifiutato");
    this.name = "CommandRefused";
  }
}
