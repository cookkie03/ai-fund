import type {
  Annotation,
  Bar,
  CommandName,
  CommandPayloads,
  CommandResult,
  Cycle,
  EquityPoint,
  Health,
  InboxItem,
  IndicatorsResponse,
  Order,
  PortfolioSnapshot,
  TickerState,
  Trade,
  WatchlistItem,
} from "./types";

/** Every Runtime call fails with this; `unreachable` separates a dead Runtime from an HTTP error. */
export class RuntimeError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly unreachable = false,
  ) {
    super(message);
    this.name = "RuntimeError";
  }
}

/** The cockpit is a client like the CLI and Telegram: it identifies itself on every write. */
export const ACTOR = "cockpit";

type Query = Record<string, string | number | boolean | null | undefined>;

function qs(params: Query = {}): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (!entries.length) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

export class RuntimeClient {
  constructor(readonly baseUrl: string) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await fetch(this.baseUrl + path, { ...init, headers: { Accept: "application/json", ...init?.headers } });
    } catch {
      throw new RuntimeError("Runtime irraggiungibile", null, true);
    }
    // The Vite proxy answers 502/504 when the Runtime process is down.
    if (res.status === 502 || res.status === 503 || res.status === 504) {
      throw new RuntimeError("Runtime irraggiungibile", res.status, true);
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch {
        /* keep statusText */
      }
      throw new RuntimeError(detail, res.status);
    }
    return (await res.json()) as T;
  }

  read<T>(name: string, params?: Query): Promise<T> {
    return this.request<T>(`/v1/read/${name}${qs(params)}`);
  }

  health = () => this.request<Health>("/v1/health");
  portfolio = () => this.read<PortfolioSnapshot | null>("portfolio");
  equityHistory = (from?: string) => this.read<EquityPoint[]>("equity_history", { from });
  orders = (status?: string, limit = 200) => this.read<Order[]>("orders", { status, limit });
  order = (id: number) => this.read<Order>("order", { id });
  trades = (params: { ticker?: string; status?: "open" | "closed"; limit?: number } = {}) =>
    this.read<Trade[]>("trades", { limit: 200, ...params });
  cycles = (params: { ticker?: string; status?: string; limit?: number } = {}) => this.read<Cycle[]>("cycles", params);
  cycle = (id: number) => this.read<Cycle>("cycle", { id });
  tickerState = (ticker: string) => this.read<TickerState>("ticker_state", { ticker });
  watchlist = () => this.read<WatchlistItem[]>("watchlist");
  inbox = (unreadOnly = false, limit = 50) => this.read<InboxItem[]>("inbox", { unread_only: unreadOnly, limit });
  bars = (ticker: string, timeframe?: string | null, limit = 500) => this.read<Bar[]>("bars", { ticker, timeframe, limit });
  indicators = (ticker: string, names: string[], timeframe?: string | null, limit = 500) =>
    this.read<IndicatorsResponse>("indicators", { ticker, names: names.join(","), timeframe, limit });
  annotations = (ticker: string, includeStruck = false) =>
    this.read<Annotation[]>("annotations", { ticker, include_struck: includeStruck });

  /** POST a command with a fresh Idempotency-Key. A domain refusal is `ok: false`, not a throw. */
  command<N extends CommandName>(name: N, payload: CommandPayloads[N], idempotencyKey = crypto.randomUUID()) {
    return this.request<CommandResult>(`/v1/commands/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey, "X-Actor": ACTOR },
      body: JSON.stringify(payload),
    });
  }

  eventsUrl(after: number | null): string {
    return `${this.baseUrl}/v1/events${after !== null ? `?after=${after}` : ""}`;
  }
}
