import { isNotExposed } from "@/features/office/api";
import { parseTs, toNum } from "@/lib/format";
import { orderFigures, RISK_LIMITS } from "@/lib/orders";
import { RuntimeError, type RuntimeClient } from "@/lib/runtime/client";
import type { Bar, CommandResult, EquityPoint, Order, PortfolioSnapshot, Trade } from "@/lib/runtime/types";
import type {
  Allocation,
  Attribution,
  ClosePositionPayload,
  ClosePreview,
  EquityPointDD,
  ExitPreview,
  GateOutcome,
  Insufficient,
  LimitUsage,
  ModifyExitPayload,
  Performance,
  Period,
  PortfolioPosition,
  PortfolioSummary,
  PortfolioTrade,
  RiskLimits,
  RiskLimitsChange,
  RiskLimitsRead,
  Sourced,
  UpdateRiskLimitsPayload,
} from "./types";

// Adapters for the Portafoglio reads. Each one asks the contract endpoint first; a 404 "Read endpoint not found"
// means the backend has not landed yet, and the adapter either rebuilds the value from real reads (`derived`,
// with a note naming the endpoint it stands in for) or says `unavailable`. Values the contract names but the
// real reads cannot give stay null: never a guess, never sample data.

type Row = Record<string, unknown>;

const str = (v: unknown): string | null => (typeof v === "string" && v.length ? v : null);
const num = (v: unknown): number | null => toNum(v);
const list = (v: unknown, key: string): Row[] => {
  if (Array.isArray(v)) return v as Row[];
  if (v && typeof v === "object" && Array.isArray((v as Row)[key])) return (v as Row)[key] as Row[];
  return [];
};

async function exposed<T>(read: () => Promise<T>, fallback: () => Promise<Sourced<T>>): Promise<Sourced<T>> {
  try {
    return { source: "runtime", data: await read() };
  } catch (err) {
    if (isNotExposed(err)) return fallback();
    throw err;
  }
}

const unavailable = (endpoint: string, what: string) => async (): Promise<Sourced<never>> => ({
  source: "unavailable",
  note: `${what} arriva con /v1/read/${endpoint}, che il Runtime non espone ancora.`,
});

/** Real reads the derived views are rebuilt from, fetched once per adapter call. */
type Base = { snapshot: PortfolioSnapshot | null; history: EquityPoint[]; trades: Trade[]; orders: Order[] };

async function base(client: RuntimeClient, parts: (keyof Base)[]): Promise<Base> {
  const want = new Set(parts);
  const [snapshot, history, trades, orders] = await Promise.all([
    want.has("snapshot") ? client.portfolio() : null,
    want.has("history") ? client.equityHistory() : [],
    want.has("trades") ? client.trades({ limit: 500 }) : [],
    want.has("orders") ? client.orders(undefined, 500) : [],
  ]);
  return { snapshot: snapshot ?? null, history: history ?? [], trades: trades ?? [], orders: orders ?? [] };
}

const DAY = 86_400_000;
// Trading days are New York dates, as in the top bar's day P&L.
const nyDay = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" });
const tradingDay = (ms: number) => nyDay.format(new Date(ms));

/** Start of a period window, or null for ALL. */
export function periodStart(period: Period, now = Date.now()): number | null {
  const d = new Date(now);
  switch (period) {
    case "1D":
      return now - DAY;
    case "1W":
      return now - 7 * DAY;
    case "1M":
      return new Date(d.getFullYear(), d.getMonth() - 1, d.getDate()).getTime();
    case "3M":
      return new Date(d.getFullYear(), d.getMonth() - 3, d.getDate()).getTime();
    case "YTD":
      return new Date(d.getFullYear(), 0, 1).getTime();
    case "1Y":
      return new Date(d.getFullYear() - 1, d.getMonth(), d.getDate()).getTime();
    default:
      return null;
  }
}

// ---------- normalizers for contract rows (tolerate strings for numbers, never rename) ----------

function normPosition(r: Row): PortfolioPosition {
  return {
    ticker: str(r.ticker) ?? "?",
    side: str(r.side) ?? "long",
    qty: num(r.qty) ?? 0,
    avg_entry_price: num(r.avg_entry_price) ?? 0,
    current_price: num(r.current_price),
    market_value: num(r.market_value),
    weight: num(r.weight),
    unrealized_pnl: num(r.unrealized_pnl),
    unrealized_pnl_fraction: num(r.unrealized_pnl_fraction),
    stop_price: num(r.stop_price),
    target_price: num(r.target_price),
    open_risk: num(r.open_risk),
    open_risk_fraction: num(r.open_risk_fraction),
    sector: str(r.sector),
    opened_ts: str(r.opened_ts),
    days_held: num(r.days_held),
    trade_id: num(r.trade_id),
    proposed_by: str(r.proposed_by),
  };
}

function normTrade(r: Row, entryOrders?: Map<number, Order>): PortfolioTrade {
  const entry = num(r.entry_price) ?? 0;
  const exit = num(r.exit_price);
  const qty = num(r.qty) ?? 0;
  const opened = str(r.opened_ts) ?? "";
  const closed = str(r.closed_ts);
  const closedOk = !!closed;
  const pnl = num(r.pnl) ?? (closedOk && exit !== null ? (exit - entry) * qty : null);
  let r_multiple = num(r.r_multiple);
  if (r_multiple === null && closedOk && exit !== null && entryOrders) {
    const o = entryOrders.get(num(r.entry_order_id) ?? -1);
    const stop = o ? orderFigures(o).stop : null;
    if (stop !== null && entry !== stop) r_multiple = (exit - entry) / (entry - stop);
  }
  const o = parseTs(opened);
  const c = parseTs(closed);
  return {
    id: num(r.id) ?? 0,
    ticker: str(r.ticker) ?? "?",
    entry_order_id: num(r.entry_order_id) ?? 0,
    exit_order_id: num(r.exit_order_id),
    entry_price: entry,
    exit_price: exit,
    qty,
    exit_reason: str(r.exit_reason),
    opened_ts: opened,
    closed_ts: closed,
    r_multiple,
    duration_s: num(r.duration_s) ?? (o !== null && c !== null ? Math.round((c - o) / 1000) : null),
    pnl,
    proposed_by: str(r.proposed_by),
  };
}

const sameTicker = (a: string | undefined, b: string) => (a ?? "").toUpperCase() === b.toUpperCase();

// ---------- 1. summary ----------

function deriveSummary(b: Base, halted: boolean): PortfolioSummary | null {
  const s = b.snapshot;
  if (!s) return null;
  const positions = s.positions ?? [];
  const invested = positions.reduce((acc, p) => acc + (num(p.market_value) ?? (num(p.qty) ?? 0) * (num(p.current_price) ?? 0)), 0);
  const unrealized = positions.reduce((acc, p) => acc + (num(p.unrealized_pl) ?? 0), 0);
  const snapMs = parseTs(s.ts) ?? Date.now();
  const today = tradingDay(snapMs);
  const prev = [...b.history].reverse().find((p) => {
    const t = parseTs(p.ts);
    return t !== null && tradingDay(t) < today;
  });
  const realizedToday = b.trades
    .filter((t) => t.closed_ts && tradingDay(parseTs(t.closed_ts) ?? 0) === today && t.exit_price !== null)
    .reduce((acc, t) => acc + ((t.exit_price ?? 0) - t.entry_price) * t.qty, 0);
  return {
    ts: s.ts,
    equity: s.equity,
    cash: s.cash,
    invested,
    cash_reserve_fraction: s.equity ? s.cash / s.equity : null,
    day_change: prev ? s.equity - prev.equity : null,
    day_change_fraction: prev && prev.equity ? s.equity / prev.equity - 1 : null,
    unrealized_pnl: unrealized,
    realized_pnl_today: realizedToday,
    positions_count: positions.length,
    snapshot_age_s: Math.max(0, Math.round((Date.now() - snapMs) / 1000)),
    halted,
  };
}

export function fetchSummary(client: RuntimeClient, halted: boolean): Promise<Sourced<PortfolioSummary | null>> {
  return exposed(
    async () => {
      const r = await client.read<Row | null>("portfolio_summary");
      // An account never synced comes back zeroed with ts null: that is "no snapshot", not $0.
      if (!r || r.ts === null || r.ts === undefined) return null;
      return {
        ts: str(r.ts) ?? "",
        equity: num(r.equity) ?? 0,
        cash: num(r.cash) ?? 0,
        invested: num(r.invested) ?? 0,
        cash_reserve_fraction: num(r.cash_reserve_fraction),
        day_change: num(r.day_change),
        day_change_fraction: num(r.day_change_fraction),
        unrealized_pnl: num(r.unrealized_pnl) ?? 0,
        realized_pnl_today: num(r.realized_pnl_today),
        positions_count: num(r.positions_count) ?? 0,
        snapshot_age_s: num(r.snapshot_age_s),
        halted: !!r.halted,
      };
    },
    async () => ({
      source: "derived",
      data: deriveSummary(await base(client, ["snapshot", "history", "trades"]), halted),
      note: "Riepilogo ricostruito da portfolio, equity_history e trades: /v1/read/portfolio_summary non è ancora esposto.",
    }),
  );
}

// ---------- 2. positions ----------

function derivePositions(b: Base): PortfolioPosition[] {
  const s = b.snapshot;
  if (!s) return [];
  const ordersById = new Map(b.orders.map((o) => [o.id, o]));
  const now = Date.now();
  return (s.positions ?? []).map((p) => {
    const ticker = (p.symbol ?? p.ticker ?? "?").toUpperCase();
    const qty = num(p.qty) ?? 0;
    const avg = num(p.avg_entry_price) ?? 0;
    const px = num(p.current_price);
    const mv = num(p.market_value) ?? (px !== null ? px * qty : null);
    const upl = num(p.unrealized_pl) ?? (px !== null ? (px - avg) * qty : null);
    const trade = b.trades.find((t) => !t.closed_ts && sameTicker(t.ticker, ticker));
    const entry = trade ? ordersById.get(trade.entry_order_id) : undefined;
    const f = entry ? orderFigures(entry) : null;
    const stop = f?.stop ?? null;
    const risk = stop !== null && px !== null ? Math.max(0, (px - stop) * qty) : null;
    const opened = trade?.opened_ts ?? null;
    const openedMs = parseTs(opened);
    return {
      ticker,
      side: qty < 0 ? "short" : "long",
      qty,
      avg_entry_price: avg,
      current_price: px,
      market_value: mv,
      weight: mv !== null && s.equity ? mv / s.equity : null,
      unrealized_pnl: upl,
      unrealized_pnl_fraction: upl !== null && avg && qty ? upl / (avg * Math.abs(qty)) : null,
      stop_price: stop,
      target_price: f?.tp ?? null,
      open_risk: risk,
      open_risk_fraction: risk !== null && s.equity ? risk / s.equity : null,
      sector: null,
      opened_ts: opened,
      days_held: openedMs !== null ? Math.floor((now - openedMs) / DAY) : null,
      trade_id: trade?.id ?? null,
      proposed_by: null,
    };
  });
}

export function fetchPositions(client: RuntimeClient): Promise<Sourced<PortfolioPosition[]>> {
  return exposed(
    async () => list(await client.read<unknown>("positions"), "positions").map(normPosition),
    async () => ({
      source: "derived",
      data: derivePositions(await base(client, ["snapshot", "trades", "orders"])),
      note: "Posizioni dal broker; stop e target dall'ordine d'ingresso, settore e agente non disponibili finché il Runtime non espone /v1/read/positions.",
    }),
  );
}

// ---------- 3. allocation ----------

export function fetchAllocation(client: RuntimeClient): Promise<Sourced<Allocation>> {
  return exposed(
    async () => {
      const r = (await client.read<Row>("allocation")) ?? {};
      const cash = (r.cash ?? {}) as Row;
      return {
        by_sector: list(r.by_sector, "").map((x) => ({ sector: str(x.sector) ?? "Altro", value: num(x.value) ?? 0, weight: num(x.weight) ?? 0, limit: num(x.limit) })),
        by_position: list(r.by_position, "").map((x) => ({ ticker: str(x.ticker) ?? "?", value: num(x.value) ?? 0, weight: num(x.weight) ?? 0, limit: num(x.limit) })),
        cash: { value: num(cash.value) ?? 0, weight: num(cash.weight) ?? 0, min_reserve: num(cash.min_reserve) },
      };
    },
    async () => {
      const b = await base(client, ["snapshot", "trades", "orders"]);
      const s = b.snapshot;
      const positions = derivePositions(b);
      return {
        source: "derived",
        data: {
          by_sector: [],
          by_position: positions
            .filter((p) => p.market_value !== null)
            .map((p) => ({ ticker: p.ticker, value: p.market_value ?? 0, weight: p.weight ?? 0, limit: RISK_LIMITS.positionPct / 100 }))
            .sort((x, y) => y.weight - x.weight),
          cash: { value: s?.cash ?? 0, weight: s && s.equity ? s.cash / s.equity : 0, min_reserve: RISK_LIMITS.cashReservePct / 100 },
        },
        note: "Pesi dalle posizioni del broker, soglie dai default di configurazione. I settori arrivano con /v1/read/allocation.",
      };
    },
  );
}

// ---------- 9. equity history (with drawdown) ----------

export function withDrawdown(points: EquityPoint[]): EquityPointDD[] {
  let peak = -Infinity;
  return points.map((p) => {
    const raw = (p as EquityPoint & { drawdown_fraction?: unknown }).drawdown_fraction;
    peak = Math.max(peak, p.equity);
    return { ts: p.ts, equity: p.equity, cash: p.cash, drawdown_fraction: num(raw) ?? (peak > 0 ? p.equity / peak - 1 : null) };
  });
}

export async function fetchEquity(client: RuntimeClient): Promise<EquityPointDD[]> {
  return withDrawdown((await client.equityHistory()) ?? []);
}

/** Daily SPY closes for the benchmark overlay; empty when the Runtime has no bars for it. */
export async function fetchBenchmarkBars(client: RuntimeClient, ticker = "SPY"): Promise<Bar[]> {
  try {
    return (await client.bars(ticker, "1d", 800)) ?? [];
  } catch (err) {
    if (err instanceof RuntimeError && !err.unreachable) return [];
    throw err;
  }
}

// ---------- 4. performance ----------

const MIN_POINTS = 2;
const MIN_TRADES = 5;
const RUNTIME_ONLY: [keyof Performance, string][] = [
  ["volatility_annualized", "Volatilità"],
  ["sharpe", "Sharpe"],
  ["sortino", "Sortino"],
];

function derivePerformance(period: Period, b: Base, spy: Bar[]): Performance {
  const start = periodStart(period);
  const pts = withDrawdown(b.history).filter((p) => start === null || (parseTs(p.ts) ?? 0) >= start);
  const insufficient: Insufficient[] = [];
  const enough = pts.length >= MIN_POINTS;
  let maxDD: number | null = null;
  let curDD: number | null = null;
  if (enough) {
    let peak = -Infinity;
    maxDD = 0;
    for (const p of pts) {
      peak = Math.max(peak, p.equity);
      maxDD = Math.min(maxDD, p.equity / peak - 1);
    }
    curDD = pts[pts.length - 1].equity / peak - 1;
  } else {
    for (const m of ["return_fraction", "max_drawdown_fraction", "current_drawdown_fraction"])
      insufficient.push({ metric: m, reason: `Servono almeno ${MIN_POINTS} punti di equity nel periodo.`, min_observations: MIN_POINTS });
  }
  for (const [m, label] of RUNTIME_ONLY) insufficient.push({ metric: m, reason: `${label} la calcola il Runtime: arriva con /v1/read/performance.`, min_observations: null });

  const closed = b.trades
    .map((t) => normTrade(t as unknown as Row, new Map(b.orders.map((o) => [o.id, o]))))
    .filter((t) => t.closed_ts && t.pnl !== null && (start === null || (parseTs(t.closed_ts) ?? 0) >= start));
  const wins = closed.filter((t) => (t.pnl ?? 0) > 0);
  const losses = closed.filter((t) => (t.pnl ?? 0) < 0);
  const tradeStats = closed.length >= MIN_TRADES;
  if (!tradeStats) {
    for (const m of ["win_rate", "profit_factor", "expectancy", "expectancy_r"])
      insufficient.push({ metric: m, reason: `Servono almeno ${MIN_TRADES} trade chiusi nel periodo (ora ${closed.length}).`, min_observations: MIN_TRADES });
  }
  const rs = closed.map((t) => t.r_multiple).filter((r): r is number => r !== null);
  const sumWin = wins.reduce((a, t) => a + (t.pnl ?? 0), 0);
  const sumLoss = Math.abs(losses.reduce((a, t) => a + (t.pnl ?? 0), 0));

  let benchmark: Performance["benchmark"] = null;
  const spyIn = spy.filter((x) => start === null || x.time * 1000 >= start);
  if (spyIn.length >= MIN_POINTS) {
    benchmark = { ticker: "SPY", return_fraction: spyIn[spyIn.length - 1].close / spyIn[0].close - 1, beta: null, correlation: null };
  }
  const unrealized = (b.snapshot?.positions ?? []).reduce((a, p) => a + (num(p.unrealized_pl) ?? 0), 0);

  return {
    period,
    from: pts[0]?.ts ?? null,
    to: pts[pts.length - 1]?.ts ?? null,
    observations: pts.length,
    return_fraction: enough ? pts[pts.length - 1].equity / pts[0].equity - 1 : null,
    realized_pnl: closed.reduce((a, t) => a + (t.pnl ?? 0), 0),
    unrealized_pnl: b.snapshot ? unrealized : null,
    max_drawdown_fraction: maxDD,
    current_drawdown_fraction: curDD,
    volatility_annualized: null,
    sharpe: null,
    sortino: null,
    win_rate: tradeStats ? wins.length / closed.length : null,
    profit_factor: tradeStats && sumLoss > 0 ? sumWin / sumLoss : null,
    expectancy: tradeStats ? closed.reduce((a, t) => a + (t.pnl ?? 0), 0) / closed.length : null,
    expectancy_r: tradeStats && rs.length >= MIN_TRADES ? rs.reduce((a, r) => a + r, 0) / rs.length : null,
    trades_closed: closed.length,
    benchmark,
    insufficient,
  };
}

function normPerformance(r: Row, period: Period): Performance {
  const bm = r.benchmark as Row | null | undefined;
  return {
    period: (str(r.period) as Period) ?? period,
    from: str(r.from),
    to: str(r.to),
    observations: num(r.observations) ?? 0,
    return_fraction: num(r.return_fraction),
    realized_pnl: num(r.realized_pnl),
    unrealized_pnl: num(r.unrealized_pnl),
    max_drawdown_fraction: num(r.max_drawdown_fraction),
    current_drawdown_fraction: num(r.current_drawdown_fraction),
    volatility_annualized: num(r.volatility_annualized),
    sharpe: num(r.sharpe),
    sortino: num(r.sortino),
    win_rate: num(r.win_rate),
    profit_factor: num(r.profit_factor),
    expectancy: num(r.expectancy),
    expectancy_r: num(r.expectancy_r),
    trades_closed: num(r.trades_closed) ?? 0,
    benchmark: bm ? { ticker: str(bm.ticker) ?? "SPY", return_fraction: num(bm.return_fraction), beta: num(bm.beta), correlation: num(bm.correlation) } : null,
    insufficient: list(r.insufficient, "").map((x) => ({ metric: str(x.metric) ?? "", reason: str(x.reason) ?? "", min_observations: num(x.min_observations) })),
  };
}

export function fetchPerformance(client: RuntimeClient, period: Period): Promise<Sourced<Performance>> {
  return exposed(
    async () => normPerformance((await client.read<Row>("performance", { period, benchmark: "SPY" })) ?? {}, period),
    async () => {
      const [b, spy] = await Promise.all([base(client, ["snapshot", "history", "trades", "orders"]), fetchBenchmarkBars(client)]);
      return {
        source: "derived",
        data: derivePerformance(period, b, spy),
        note: "Rendimento e drawdown da equity_history, statistiche dai trade chiusi. Volatilità, Sharpe, Sortino, beta e correlazione arrivano con /v1/read/performance.",
      };
    },
  );
}

// ---------- 5. attribution ----------

export function fetchAttribution(client: RuntimeClient, period: Period): Promise<Sourced<Attribution>> {
  return exposed(
    async () => {
      const r = (await client.read<Row>("attribution", { period })) ?? {};
      return {
        by_position: list(r.by_position, "").map((x) => ({ ticker: str(x.ticker) ?? "?", pnl: num(x.pnl) ?? 0, contribution_fraction: num(x.contribution_fraction) ?? 0 })),
        by_sector: list(r.by_sector, "").map((x) => ({ sector: str(x.sector) ?? "Altro", pnl: num(x.pnl) ?? 0, contribution_fraction: num(x.contribution_fraction) ?? 0 })),
        by_agent: list(r.by_agent, "").map((x) => ({ agent: str(x.agent) ?? "?", pnl: num(x.pnl) ?? 0, contribution_fraction: num(x.contribution_fraction) ?? 0, trades: num(x.trades) ?? 0 })),
      };
    },
    async () => {
      const b = await base(client, ["snapshot", "history", "trades"]);
      const start = periodStart(period);
      const startEquity = b.history.find((p) => start === null || (parseTs(p.ts) ?? 0) >= start)?.equity ?? b.snapshot?.equity ?? 0;
      const byTicker = new Map<string, number>();
      for (const t of b.trades) {
        if (!t.closed_ts || t.exit_price === null) continue;
        if (start !== null && (parseTs(t.closed_ts) ?? 0) < start) continue;
        byTicker.set(t.ticker, (byTicker.get(t.ticker) ?? 0) + (t.exit_price - t.entry_price) * t.qty);
      }
      for (const p of b.snapshot?.positions ?? []) {
        const tk = (p.symbol ?? p.ticker ?? "").toUpperCase();
        if (tk) byTicker.set(tk, (byTicker.get(tk) ?? 0) + (num(p.unrealized_pl) ?? 0));
      }
      return {
        source: "derived",
        data: {
          by_position: [...byTicker].map(([ticker, pnl]) => ({ ticker, pnl, contribution_fraction: startEquity ? pnl / startEquity : 0 })).sort((x, y) => y.pnl - x.pnl),
          by_sector: [],
          by_agent: [],
        },
        note: "Contributo per posizione da trade chiusi e PnL aperto. Settore e agente proponente arrivano con /v1/read/attribution.",
      };
    },
  );
}

// ---------- 6. trades ----------

export async function fetchTrades(client: RuntimeClient): Promise<{ trades: PortfolioTrade[]; enriched: boolean }> {
  const [trades, orders] = await Promise.all([client.trades({ limit: 500 }), client.orders(undefined, 500).catch(() => [] as Order[])]);
  const byId = new Map(orders.map((o) => [o.id, o]));
  const raw = (trades ?? []) as unknown as Row[];
  const enriched = raw.some((t) => "r_multiple" in t || "proposed_by" in t);
  return { trades: raw.map((t) => normTrade(t, byId)), enriched };
}

// ---------- 7, 8. risk limits ----------

const DEFAULT_LIMITS: RiskLimits = {
  max_risk_per_trade_fraction: RISK_LIMITS.tradeRiskPct / 100,
  max_position_fraction: RISK_LIMITS.positionPct / 100,
  max_sector_fraction: RISK_LIMITS.sectorPct / 100,
  max_open_positions: RISK_LIMITS.maxPositions,
  min_cash_reserve_fraction: RISK_LIMITS.cashReservePct / 100,
  min_risk_reward_ratio: RISK_LIMITS.minRR,
  earnings_embargo_days: RISK_LIMITS.earningsEmbargoDays,
};

const statusOf = (current: number | null, threshold: number, min = false): LimitUsage["status"] => {
  if (current === null) return "ok";
  if (min) return current < threshold ? "breach" : current < threshold * 1.25 ? "near" : "ok";
  return current > threshold + 1e-9 ? "breach" : current >= threshold * 0.8 ? "near" : "ok";
};

function deriveUsage(b: Base, limits: RiskLimits): LimitUsage[] {
  const pos = derivePositions(b);
  const s = b.snapshot;
  const maxW = pos.reduce((m, p) => Math.max(m, p.weight ?? 0), 0);
  const maxR = pos.reduce((m, p) => Math.max(m, p.open_risk_fraction ?? 0), 0);
  const cash = s && s.equity ? s.cash / s.equity : null;
  const widest = pos.find((p) => (p.weight ?? 0) === maxW)?.ticker;
  const riskiest = pos.find((p) => (p.open_risk_fraction ?? 0) === maxR)?.ticker;
  return [
    { limit: "max_risk_per_trade_fraction", current: pos.length ? maxR : null, threshold: limits.max_risk_per_trade_fraction, status: statusOf(pos.length ? maxR : null, limits.max_risk_per_trade_fraction), detail: riskiest ? `Rischio aperto più alto: ${riskiest}` : null },
    { limit: "max_position_fraction", current: pos.length ? maxW : null, threshold: limits.max_position_fraction, status: statusOf(pos.length ? maxW : null, limits.max_position_fraction), detail: widest ? `Posizione più pesante: ${widest}` : null },
    { limit: "max_sector_fraction", current: null, threshold: limits.max_sector_fraction, status: "ok", detail: "Settori non ancora esposti dal Runtime" },
    { limit: "max_open_positions", current: pos.length, threshold: limits.max_open_positions, status: statusOf(pos.length, limits.max_open_positions), detail: null },
    { limit: "min_cash_reserve_fraction", current: cash, threshold: limits.min_cash_reserve_fraction, status: statusOf(cash, limits.min_cash_reserve_fraction, true), detail: null },
    { limit: "min_risk_reward_ratio", current: null, threshold: limits.min_risk_reward_ratio, status: "ok", detail: "Verificato dal Risk Gate su ogni ordine" },
    { limit: "earnings_embargo_days", current: null, threshold: limits.earnings_embargo_days, status: "ok", detail: "Verificato dal Risk Gate su ogni ordine" },
  ];
}

export function fetchRiskLimits(client: RuntimeClient): Promise<Sourced<RiskLimitsRead>> {
  return exposed(
    async () => {
      const r = (await client.read<Row>("risk_limits")) ?? {};
      const limits = { ...DEFAULT_LIMITS };
      const rl = (r.limits ?? {}) as Row;
      for (const k of Object.keys(limits) as (keyof RiskLimits)[]) limits[k] = num(rl[k]) ?? limits[k];
      const bounds: RiskLimitsRead["bounds"] = {};
      for (const [k, v] of Object.entries((r.bounds ?? {}) as Record<string, Row>)) {
        const min = num(v?.min);
        const max = num(v?.max);
        if (min !== null && max !== null) bounds[k as keyof RiskLimits] = { min, max };
      }
      return {
        version: num(r.version) ?? 0,
        updated_ts: str(r.updated_ts),
        updated_by: str(r.updated_by),
        limits,
        bounds,
        usage: list(r.usage, "").map((u) => {
          const st = str(u.status);
          return { limit: str(u.limit) ?? "", current: num(u.current), threshold: num(u.threshold) ?? 0, status: st === "near" || st === "breach" ? st : "ok", detail: str(u.detail) };
        }),
      };
    },
    async () => {
      const b = await base(client, ["snapshot", "trades", "orders"]);
      return {
        source: "derived",
        data: { version: 0, updated_ts: null, updated_by: null, limits: DEFAULT_LIMITS, bounds: {}, usage: deriveUsage(b, DEFAULT_LIMITS) },
        note: "Soglie dai default di configurazione (config/office.toml), utilizzo dalle posizioni. Lettura e modifica arrivano con /v1/read/risk_limits e update_risk_limits.",
      };
    },
  );
}

export function fetchRiskHistory(client: RuntimeClient, limit = 50): Promise<Sourced<RiskLimitsChange[]>> {
  return exposed(
    async () =>
      list(await client.read<unknown>("risk_limits_history", { limit }), "history").map((r) => ({
        version: num(r.version) ?? 0,
        ts: str(r.ts) ?? "",
        actor: str(r.actor) ?? "",
        reason: str(r.reason) ?? "",
        before: (r.before ?? {}) as Partial<RiskLimits>,
        after: (r.after ?? {}) as Partial<RiskLimits>,
      })),
    unavailable("risk_limits_history", "Lo storico delle modifiche"),
  );
}

// ---------- commands ----------

/** The Runtime answers 404 "Command 'x' not found" for commands it does not have yet. */
export function isCommandMissing(err: unknown): boolean {
  return err instanceof RuntimeError && err.status === 404 && /command/i.test(err.message);
}

/** The Runtime's `risk_gate: {allowed, reasons}` from a dry run. */
function gateOf(v: unknown): GateOutcome | null {
  if (!v || typeof v !== "object") return null;
  const g = v as Row;
  return { ok: g.allowed !== false, reasons: Array.isArray(g.reasons) ? (g.reasons as unknown[]).map(String) : [] };
}

export function normClosePreview(d: Row, fallbackTicker: string): ClosePreview {
  return {
    ticker: str(d.ticker) ?? fallbackTicker,
    qty: num(d.qty),
    remaining_qty: num(d.qty_remaining_after),
    est_price: num(d.reference_price),
    est_value: num(d.estimated_value),
    realized_pnl: num(d.estimated_realized_pnl),
    gate: gateOf(d.risk_gate),
  };
}

export function normExitPreview(d: Row, fallbackTicker: string): ExitPreview {
  return {
    ticker: str(d.ticker) ?? fallbackTicker,
    qty: num(d.qty),
    stop_price_before: num(d.previous_stop_price),
    stop_price: num(d.stop_price),
    target_price_before: num(d.previous_target_price),
    target_price: num(d.target_price),
    open_risk_before: num(d.open_risk_before),
    open_risk: num(d.open_risk),
    open_risk_fraction: num(d.open_risk_fraction),
    gate: gateOf(d.risk_gate),
  };
}

export type CommandOutcome<T> = { ok: true; data: T; raw: CommandResult } | { ok: false; reasons: string[]; data: T | null };

async function run<T>(client: RuntimeClient, name: string, payload: object, norm: (d: Row) => T): Promise<CommandOutcome<T>> {
  // The three Portafoglio commands are not in the typed CommandName union until the backend lands.
  const send = client.command.bind(client) as unknown as (n: string, p: object) => Promise<CommandResult>;
  const res = await send(name, payload);
  const data = res.data && typeof res.data === "object" ? norm(res.data as Row) : null;
  if (!res.ok) return { ok: false, reasons: res.reasons ?? [], data };
  return { ok: true, data: data as T, raw: res };
}

export const closePosition = (client: RuntimeClient, p: ClosePositionPayload) => run(client, "close_position", p, (d) => normClosePreview(d, p.ticker));
export const modifyExit = (client: RuntimeClient, p: ModifyExitPayload) => run(client, "modify_exit", p, (d) => normExitPreview(d, p.ticker));
export const updateRiskLimits = (client: RuntimeClient, p: UpdateRiskLimitsPayload) => run(client, "update_risk_limits", p, (d) => d);
