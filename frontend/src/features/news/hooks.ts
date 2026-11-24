import { useInfiniteQuery, useQuery, useQueryClient, type InfiniteData } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useRuntime } from "@/lib/runtime/provider";
import type { RuntimeEvent } from "@/lib/runtime/types";
import { fetchCalendar, fetchNews, fetchNewsItem, fetchSources, PAGE_SIZE } from "./api";
import type { NewsFilters, NewsPage, NewsScope, Read, UsageKind } from "./types";

// Keys start with the read's name. The feed never refetches on its own: new items wait behind the
// "N nuove" bar (news_head), so what Luca is reading never moves under him.

const SCOPES: NewsScope[] = ["all", "portfolio", "watchlist"];
const FILTER_KEYS = ["ticker", "theme", "source_id", "provider", "q"] as const;

export function useNewsFilters() {
  const [params, setParams] = useSearchParams();
  const filters: NewsFilters = useMemo(() => {
    const scope = params.get("scope") as NewsScope | null;
    return {
      scope: scope && SCOPES.includes(scope) ? scope : "all",
      ticker: (params.get("ticker") ?? "").toUpperCase(),
      theme: params.get("theme") ?? "",
      source_id: params.get("source_id") ?? "",
      provider: params.get("provider") ?? "",
      q: params.get("q") ?? "",
    };
  }, [params]);
  const selected = Number(params.get("id")) || null;

  const update = (patch: Record<string, string | null>, opts: { push?: boolean } = {}) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(patch)) {
          if (v === null || v === "" || (k === "scope" && v === "all")) next.delete(k);
          else next.set(k, v);
        }
        return next;
      },
      { replace: !opts.push },
    );

  const setFilter = (key: keyof NewsFilters, value: string) => update({ [key]: value });
  const clearFilters = () => update(Object.fromEntries([...FILTER_KEYS, "scope"].map((k) => [k, null])));
  const select = (id: number | null, opts: { push?: boolean } = {}) => update({ id: id === null ? null : String(id) }, opts);
  const active = FILTER_KEYS.filter((k) => filters[k]).length + (filters.scope !== "all" ? 1 : 0);
  return { filters, selected, setFilter, clearFilters, select, active };
}

const filterKey = (f: NewsFilters) => [f.scope, f.ticker, f.theme, f.source_id, f.provider, f.q].join("|");

export function useNewsFeed(f: NewsFilters) {
  const { client, target } = useRuntime();
  return useInfiniteQuery({
    queryKey: ["news_feed", target.id, filterKey(f)],
    queryFn: ({ pageParam }) => fetchNews(client, f, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last: Read<NewsPage>) => (last.state === "ok" ? last.data.next_before : null) ?? undefined,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

/** The newest page for the same filters, refreshed on `news.ingested` (and every minute if the stream is quiet). */
export function useNewsHead(f: NewsFilters, enabled: boolean) {
  const { client, target } = useRuntime();
  return useQuery({
    queryKey: ["news_head", target.id, filterKey(f)],
    queryFn: () => fetchNews(client, f, null, PAGE_SIZE),
    enabled,
    refetchInterval: 60_000,
    staleTime: 0,
  });
}

export function useNewsItem(id: number | null) {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["news_item", target.id, id], queryFn: () => fetchNewsItem(client, id!), enabled: id !== null, refetchInterval: 60_000 });
}

export function useNewsSources() {
  const { client, target } = useRuntime();
  return useQuery({ queryKey: ["news_sources", target.id], queryFn: () => fetchSources(client), refetchInterval: 60_000 });
}

function dayStart(offsetDays: number): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString();
}

/** Today and the next `days` days. The boundary is fixed per day so the key is stable. */
export function useCalendar(days = 7) {
  const { client, target } = useRuntime();
  const from = dayStart(0);
  const to = dayStart(days + 1);
  return useQuery({ queryKey: ["news_calendar", target.id, from, to], queryFn: () => fetchCalendar(client, from, to), refetchInterval: 300_000 });
}

const USAGE_FIELD: Record<UsageKind, "reads" | "citations" | "forwards"> = { read: "reads", cited: "citations", forwarded: "forwards" };

/**
 * Applies the news events: `news.ingested` refreshes the head (the "N nuove" count) and the sources,
 * `news.used` bumps the row's usage mark in place and reloads that item's trace, `news.source` reloads sources.
 * With COCKPIT_NEWS_FIXTURES the dev server sends synthetic events on its own stream; a build never opens it.
 */
export function useNewsLive() {
  const { onEvent, target } = useRuntime();
  const qc = useQueryClient();
  useEffect(() => {
    const apply = (e: RuntimeEvent) => {
      if (e.type === "news.ingested") {
        qc.invalidateQueries({ queryKey: ["news_head"] });
        qc.invalidateQueries({ queryKey: ["news_sources"] });
      } else if (e.type === "news.source") {
        qc.invalidateQueries({ queryKey: ["news_sources"] });
      } else if (e.type === "news.used") {
        const id = Number(e.data.news_id);
        const kind = e.data.kind as UsageKind;
        qc.invalidateQueries({ queryKey: ["news_item", target.id, id] });
        if (!USAGE_FIELD[kind]) return;
        qc.setQueriesData<InfiniteData<Read<NewsPage>>>({ queryKey: ["news_feed"] }, (old) =>
          old && {
            ...old,
            pages: old.pages.map((p) =>
              p.state !== "ok"
                ? p
                : { ...p, data: { ...p.data, items: p.data.items.map((n) => (n.id === id ? { ...n, usage: { ...n.usage, [USAGE_FIELD[kind]]: n.usage[USAGE_FIELD[kind]] + 1 } } : n)) } },
            ),
          },
        );
      }
    };
    const off = onEvent(apply);
    let dev: EventSource | null = null;
    if (import.meta.env.VITE_NEWS_FIXTURES === "1") {
      dev = new EventSource("/v1/dev/news-events");
      for (const type of ["news.ingested", "news.used", "news.source"])
        dev.addEventListener(type, (raw) => {
          try {
            apply({ id: 0, type, data: JSON.parse((raw as MessageEvent).data) });
          } catch {
            /* malformed dev event */
          }
        });
    }
    return () => {
      off();
      dev?.close();
    };
  }, [onEvent, qc, target.id]);
}
