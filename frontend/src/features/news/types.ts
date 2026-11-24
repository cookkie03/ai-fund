// Field names are the contract's, verbatim (.scratch/notizie/handoff-backend.md, "Contratto").

export type NewsProvider = "alpaca" | "rss" | "openbb";

export type NewsUsage = { reads: number; citations: number; forwards: number };

export type NewsItem = {
  id: number;
  headline: string;
  summary: string | null;
  url: string | null;
  source: string;
  provider: NewsProvider | string;
  published_ts: string;
  fetched_ts: string;
  tickers: string[];
  themes: string[];
  image_url: string | null;
  has_full_text: boolean;
  in_portfolio: boolean;
  in_watchlist: boolean;
  usage: NewsUsage;
};

export type UsageKind = "read" | "cited" | "forwarded";

export type UsageEntry = {
  agent: string;
  kind: UsageKind;
  ts: string;
  cycle_id: number | null;
  chat_id: number | null;
  topic: string | null;
  note: string | null;
};

export type NewsDetail = NewsItem & { full_text: string | null; usage_detail: UsageEntry[] };

export type NewsPage = { items: NewsItem[]; next_before: string | null };

export type SourceStatus = "ok" | "error" | "unavailable";

export type NewsSource = {
  id: number;
  provider: NewsProvider | string;
  name: string;
  url: string | null;
  enabled: boolean;
  status: SourceStatus;
  last_fetch_ts: string | null;
  last_error: string | null;
  items_24h: number;
};

export type Importance = "low" | "medium" | "high";

export type CalendarEvent = {
  id: number | string;
  kind: "macro" | "earnings";
  ts: string;
  title: string;
  country: string | null;
  ticker: string | null;
  importance: Importance | null;
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  source: string;
  in_portfolio: boolean;
  in_watchlist: boolean;
};

export type NewsScope = "all" | "portfolio" | "watchlist";

/** The feed's filters, mirrored in the URL. Empty strings mean "no filter". */
export type NewsFilters = {
  scope: NewsScope;
  ticker: string;
  theme: string;
  source_id: string;
  provider: string;
  q: string;
};

/** A read the Runtime may not expose yet: `unavailable` names the endpoint it waits for. */
export type Read<T> = { state: "ok"; data: T } | { state: "unavailable"; endpoint: string } | { state: "missing" };

/** Where a forward goes: one agent, or a ticker (its `ticker:<SYM>` agent, else the PM, in the ticker's topic). */
export type ForwardTarget = { agent: string } | { ticker: string };
