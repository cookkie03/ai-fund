// Development only. Answers the Ufficio reads the Runtime does not expose yet (`agents`, `tool_calls`, `usage`)
// with synthetic data shaped like the proposed contract, so every state of the page can be designed and
// checked before `backend-ufficio` lands. Enabled only by `COCKPIT_OFFICE_FIXTURES=1` on `vite` (serve):
// it never reaches a build. Chats stay real: they come from the Runtime (or the synthetic dev Runtime).
import type { Plugin } from "vite";

const AGENTS = ["portfolio_manager", "technical_analyst", "market_analyst", "sentiment_analyst", "fundamental_analyst", "risk_analyst"];

const iso = (msAgo: number) => new Date(Date.now() - msAgo).toISOString();
const MIN = 60_000;

function agents() {
  return [
    { name: "portfolio_manager", role: null, model: "my-combo", status: "working", current: { kind: "cycle", id: 2, ticker: "NVDA", label: "Decide sulla bozza NVDA" }, last_activity_ts: iso(2 * MIN), today: { tokens_in: 412_300, tokens_out: 38_900, cost: 1.84, calls: 41 } },
    { name: "technical_analyst", role: null, model: "my-combo", status: "working", current: { kind: "cycle", id: 3, ticker: "AMD", label: "Rilegge il supporto su AMD" }, last_activity_ts: iso(25_000), today: { tokens_in: 268_100, tokens_out: 21_400, cost: 0.96, calls: 57 } },
    { name: "market_analyst", role: null, model: "my-combo", status: "waiting", current: { kind: "task", id: 14, ticker: "MSFT", label: "Task in coda alle 16:30" }, last_activity_ts: iso(38 * MIN), today: { tokens_in: 120_800, tokens_out: 9_700, cost: 0.41, calls: 18 } },
    { name: "sentiment_analyst", role: null, model: "my-combo", status: "idle", current: null, last_activity_ts: iso(3 * 60 * MIN), today: { tokens_in: 64_200, tokens_out: 5_100, cost: 0.19, calls: 9 } },
    { name: "fundamental_analyst", role: null, model: "my-combo", status: "idle", current: null, last_activity_ts: iso(26 * 60 * MIN), today: { tokens_in: 0, tokens_out: 0, cost: 0, calls: 0 } },
    { name: "risk_analyst", role: null, model: "my-combo", status: "waiting", current: { kind: "cycle", id: 2, ticker: "NVDA", label: "Attende la bozza del PM" }, last_activity_ts: iso(11 * MIN), today: { tokens_in: 88_000, tokens_out: 6_300, cost: 0.27, calls: 12 } },
  ];
}

type Call = Record<string, unknown>;

const BARS_RESULT = { ticker: "AMD", timeframe: "1h", bars: 120, last: { time: 1795449600, open: 138.2, high: 139.9, low: 137.6, close: 139.4, volume: 2_140_000 } };

function toolCalls(agent: string): Call[] {
  // A new call starts every 20 s and finishes after 8 s, so the stream visibly moves while you watch.
  const bucket = Math.floor(Date.now() / 20_000);
  const age = Date.now() - bucket * 20_000;
  const live: Call[] = [
    {
      id: 1000 + bucket,
      ts: new Date(bucket * 20_000).toISOString(),
      agent,
      topic: "AMD",
      cycle_id: 3,
      tool: bucket % 2 ? "get_bars" : "get_indicators",
      params: bucket % 2 ? { ticker: "AMD", timeframe: "1h", limit: 120 } : { ticker: "AMD", names: ["ema20", "rsi14", "atr14"] },
      result: age > 8000 ? BARS_RESULT : null,
      status: age > 8000 ? "ok" : "running",
      error: null,
      duration_ms: age > 8000 ? 1420 + (bucket % 7) * 130 : null,
      compacted: { params: false, result: false, at: null },
    },
  ];
  const history: Call[] = [
    { id: 990, ts: iso(1.5 * MIN), tool: "read_annotations", params: { ticker: "AMD", include_struck: false }, result: [{ id: "a-12", author: "luca", type: "horizontal_line", price: 136.5 }], status: "ok", duration_ms: 84 },
    { id: 989, ts: iso(3 * MIN), tool: "get_news", params: { ticker: "AMD", since: "24h", limit: 10 }, result: null, status: "error", error: "Provider notizie: timeout dopo 10 s (retry 2/2)", duration_ms: 10_012 },
    { id: 988, ts: iso(4 * MIN), tool: "get_ticker_state", params: { ticker: "AMD" }, result: { analyses: { technical_analyst: "Rimbalzo sul supporto, segnale debole." }, decision: null }, status: "ok", duration_ms: 46 },
    { id: 987, ts: iso(6 * MIN), tool: "upsert_annotation", params: { ticker: "AMD", drawing: { type: "horizontal_line", price: 137.2, text: "supporto 137,2" } }, result: { ok: true, id: "ta-88" }, status: "ok", duration_ms: 31 },
    { id: 986, ts: iso(9 * MIN), tool: "get_bars", params: { ticker: "NVDA", timeframe: "15m", limit: 200 }, result: { ticker: "NVDA", bars: 200 }, status: "ok", duration_ms: 1_210 },
    { id: 940, ts: iso(26 * 60 * MIN), tool: "get_fundamentals", params: { ticker: "AAPL", period: "quarterly" }, result: null, status: "ok", duration_ms: 2_330, compacted: { params: false, result: true, at: iso(2 * 60 * MIN) } },
    { id: 939, ts: iso(27 * 60 * MIN), tool: "search_filings", params: null, result: null, status: "ok", duration_ms: 3_880, compacted: { params: true, result: true, at: iso(2 * 60 * MIN) } },
  ].map((c) => ({ agent, topic: "AMD", cycle_id: 3, error: null, compacted: { params: false, result: false, at: null }, ...c }));
  if (agent === "fundamental_analyst") return [];
  return [...live, ...history];
}

function usage(agent: string | null, from: string | null) {
  const days = from ? Math.max(1, Math.round((Date.now() - Date.parse(from)) / 86_400_000)) : 1;
  const rows = agents().map((a) => ({ agent: a.name, ...a.today }));
  const scaled = rows.map((r) => ({ ...r, tokens_in: r.tokens_in * days, tokens_out: r.tokens_out * days, cost: +(r.cost * days).toFixed(3), calls: r.calls * days }));
  return agent ? scaled.filter((r) => r.agent === agent) : scaled;
}

export function officeFixtures(): Plugin {
  return {
    name: "cockpit-office-fixtures",
    apply: "serve",
    configureServer(server) {
      server.config.logger.info("  ⚠ Ufficio: fixture di sviluppo attive per agents, tool_calls, usage (COCKPIT_OFFICE_FIXTURES=1)");
      server.middlewares.use((req, res, next) => {
        const url = new URL(req.url ?? "/", "http://dev");
        const m = url.pathname.match(/^\/v1\/read\/(agents|tool_calls|usage)$/);
        if (!m) return next();
        const agent = url.searchParams.get("agent");
        const body = m[1] === "agents" ? agents() : m[1] === "tool_calls" ? (agent && AGENTS.includes(agent) ? toolCalls(agent) : []) : usage(agent, url.searchParams.get("from"));
        res.setHeader("Content-Type", "application/json");
        res.setHeader("X-Dev-Fixture", "office");
        res.end(JSON.stringify(body));
      });
    },
  };
}
