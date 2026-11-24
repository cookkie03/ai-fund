import { isNotExposed } from "@/features/office/api";
import { RuntimeError, type RuntimeClient } from "@/lib/runtime/client";
import type { CalendarEvent, Importance, NewsDetail, NewsFilters, NewsItem, NewsPage, NewsSource, Read, SourceStatus, UsageEntry, UsageKind } from "./types";

// Adapters for the news reads. They read exactly the contract's field names
// (.scratch/notizie/handoff-backend.md) and only coerce types: no aliases, no guessed names.
// A 404 "Read endpoint 'x' not found" means the Runtime predates the contract: `unavailable` + endpoint.

type Row = Record<string, unknown>;

const obj = (v: unknown): Row | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Row) : null);
const arr = (v: unknown): Row[] => (Array.isArray(v) ? (v.filter((x) => obj(x)) as Row[]) : []);
const str = (v: unknown): string | null => (typeof v === "string" && v.length ? v : typeof v === "number" ? String(v) : null);
const num = (v: unknown): number | null => {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
};
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.map(str).filter((s): s is string => !!s) : []);

export const ENDPOINT = {
  news: "GET /v1/read/news",
  item: "GET /v1/read/news_item",
  sources: "GET /v1/read/news_sources",
  calendar: "GET /v1/read/calendar",
} as const;

export const COMMAND_ENDPOINT = (name: string) => `POST /v1/commands/${name}`;

/** The Runtime answers 404 "Command 'x' not found" for commands it does not have yet. */
export function isCommandMissing(err: unknown): boolean {
  return err instanceof RuntimeError && err.status === 404 && /command '.*' not found/i.test(err.message);
}

async function guarded<T>(endpoint: string, read: () => Promise<T | null>): Promise<Read<T>> {
  try {
    const data = await read();
    return data === null ? { state: "missing" } : { state: "ok", data };
  } catch (err) {
    if (isNotExposed(err)) return { state: "unavailable", endpoint };
    if (err instanceof RuntimeError && err.status === 404) return { state: "missing" };
    throw err;
  }
}

function item(r: Row): NewsItem {
  const u = obj(r.usage);
  return {
    id: num(r.id) ?? 0,
    headline: str(r.headline) ?? "",
    summary: str(r.summary),
    url: str(r.url),
    source: str(r.source) ?? "",
    provider: str(r.provider) ?? "",
    published_ts: str(r.published_ts) ?? "",
    fetched_ts: str(r.fetched_ts) ?? "",
    tickers: strs(r.tickers),
    themes: strs(r.themes),
    image_url: str(r.image_url),
    has_full_text: r.has_full_text === true,
    in_portfolio: r.in_portfolio === true,
    in_watchlist: r.in_watchlist === true,
    usage: { reads: num(u?.reads) ?? 0, citations: num(u?.citations) ?? 0, forwards: num(u?.forwards) ?? 0 },
  };
}

const KINDS: UsageKind[] = ["read", "cited", "forwarded"];

function usage(r: Row): UsageEntry {
  const kind = str(r.kind);
  return {
    agent: str(r.agent) ?? "",
    kind: KINDS.includes(kind as UsageKind) ? (kind as UsageKind) : "read",
    ts: str(r.ts) ?? "",
    cycle_id: num(r.cycle_id),
    chat_id: num(r.chat_id),
    topic: str(r.topic),
    note: str(r.note),
  };
}

const STATUSES: SourceStatus[] = ["ok", "error", "unavailable"];

function source(r: Row): NewsSource {
  const status = str(r.status);
  return {
    id: num(r.id) ?? 0,
    provider: str(r.provider) ?? "",
    name: str(r.name) ?? "",
    url: str(r.url),
    enabled: r.enabled === true,
    status: STATUSES.includes(status as SourceStatus) ? (status as SourceStatus) : "unavailable",
    last_fetch_ts: str(r.last_fetch_ts),
    last_error: str(r.last_error),
    items_24h: num(r.items_24h) ?? 0,
  };
}

const IMPORTANCE: Importance[] = ["low", "medium", "high"];

function event(r: Row): CalendarEvent {
  const imp = str(r.importance);
  return {
    id: str(r.id) ?? "",
    kind: r.kind === "earnings" ? "earnings" : "macro",
    ts: str(r.ts) ?? "",
    title: str(r.title) ?? "",
    country: str(r.country),
    ticker: str(r.ticker),
    importance: IMPORTANCE.includes(imp as Importance) ? (imp as Importance) : null,
    actual: str(r.actual),
    forecast: str(r.forecast),
    previous: str(r.previous),
    source: str(r.source) ?? "",
    in_portfolio: r.in_portfolio === true,
    in_watchlist: r.in_watchlist === true,
  };
}

export const PAGE_SIZE = 50;

export function fetchNews(client: RuntimeClient, f: NewsFilters, before: string | null, limit = PAGE_SIZE): Promise<Read<NewsPage>> {
  return guarded(ENDPOINT.news, async () => {
    const raw = obj(
      await client.read<unknown>("news", {
        ticker: f.ticker,
        theme: f.theme,
        source_id: f.source_id,
        provider: f.provider,
        scope: f.scope === "all" ? undefined : f.scope,
        q: f.q,
        before,
        limit,
      }),
    );
    return { items: arr(raw?.items).map(item), next_before: str(raw?.next_before) };
  });
}

export function fetchNewsItem(client: RuntimeClient, id: number): Promise<Read<NewsDetail>> {
  return guarded(ENDPOINT.item, async () => {
    const r = obj(await client.read<unknown>("news_item", { id }));
    if (!r) return null;
    return { ...item(r), full_text: str(r.full_text), usage_detail: arr(r.usage_detail).map(usage) };
  });
}

export function fetchSources(client: RuntimeClient): Promise<Read<NewsSource[]>> {
  return guarded(ENDPOINT.sources, async () => arr(await client.read<unknown>("news_sources")).map(source));
}

export function fetchCalendar(client: RuntimeClient, from: string, to: string, kind?: "macro" | "earnings"): Promise<Read<CalendarEvent[]>> {
  return guarded(ENDPOINT.calendar, async () =>
    arr(await client.read<unknown>("calendar", { from, to, kind }))
      .map(event)
      .sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts)),
  );
}
