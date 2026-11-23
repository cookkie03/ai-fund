// Development only. Answers the Portafoglio reads and commands the Runtime does not expose yet, with synthetic
// data shaped exactly like the contract in .scratch/cockpit/handoff-backend-portafoglio.md, so every state of
// the page can be designed before `portafoglio-backend` lands. Enabled only by `COCKPIT_PORTFOLIO_FIXTURES=1` on
// `vite` (serve): it never reaches a build. It also overrides `equity_history`, `trades` and SPY daily `bars`
// so the curve, the metrics and the benchmark have a year of history. Orders stay real (dev Runtime).
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

const DAY = 86_400_000;
const iso = (ms: number) => new Date(ms).toISOString();

/** Deterministic PRNG so the fixture looks the same on every reload. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

type Pos = { ticker: string; qty: number; avg: number; px: number; sector: string; stop: number; target: number; agent: string | null; daysAgo: number; tradeId: number };

const state = {
  cash: 60_840,
  halted: false,
  positions: [
    { ticker: "NVDA", qty: 65, avg: 128.4, px: 141.2, sector: "Tecnologia", stop: 132, target: 158, agent: "technical_analyst", daysAgo: 21, tradeId: 101 },
    { ticker: "MSFT", qty: 18, avg: 412, px: 421.5, sector: "Tecnologia", stop: 398, target: 455, agent: "portfolio_manager", daysAgo: 34, tradeId: 102 },
    { ticker: "AMD", qty: 45, avg: 152, px: 146.3, sector: "Tecnologia", stop: 141, target: 172, agent: "technical_analyst", daysAgo: 9, tradeId: 103 },
    { ticker: "AAPL", qty: 30, avg: 236.72, px: 229, sector: "Tecnologia", stop: 224, target: 255, agent: "market_analyst", daysAgo: 4, tradeId: 104 },
    { ticker: "LLY", qty: 6, avg: 774.62, px: 812, sector: "Sanità", stop: 760, target: 860, agent: "fundamental_analyst", daysAgo: 9, tradeId: 105 },
    { ticker: "UNH", qty: 10, avg: 518, px: 531, sector: "Sanità", stop: 498, target: 570, agent: "fundamental_analyst", daysAgo: 47, tradeId: 106 },
    { ticker: "JPM", qty: 28, avg: 248, px: 262, sector: "Finanza", stop: 241, target: 280, agent: "market_analyst", daysAgo: 16, tradeId: 107 },
    { ticker: "XOM", qty: 40, avg: 116, px: 112.8, sector: "Energia", stop: 109, target: 126, agent: null, daysAgo: 12, tradeId: 108 },
  ] as Pos[],
  limits: {
    max_risk_per_trade_fraction: 0.01,
    max_position_fraction: 0.1,
    max_sector_fraction: 0.3,
    max_open_positions: 30,
    min_cash_reserve_fraction: 0.05,
    min_risk_reward_ratio: 1.5,
    earnings_embargo_days: 2,
  } as Record<string, number>,
  version: 3,
  updatedTs: iso(Date.now() - 6 * DAY),
  updatedBy: "cockpit",
  history: [
    { version: 3, ts: iso(Date.now() - 6 * DAY), actor: "cockpit", reason: "Riduco il peso massimo dopo la volatilità di ottobre", before: { max_position_fraction: 0.12 }, after: { max_position_fraction: 0.1 } },
    { version: 2, ts: iso(Date.now() - 41 * DAY), actor: "cockpit", reason: "R:R minimo più severo per i breakout", before: { min_risk_reward_ratio: 1.3 }, after: { min_risk_reward_ratio: 1.5 } },
  ] as { version: number; ts: string; actor: string; reason: string; before: Record<string, number>; after: Record<string, number> }[],
  closedExtra: [] as Record<string, unknown>[],
};

const BOUNDS: Record<string, { min: number; max: number }> = {
  max_risk_per_trade_fraction: { min: 0.001, max: 0.05 },
  max_position_fraction: { min: 0.01, max: 0.25 },
  max_sector_fraction: { min: 0.05, max: 0.6 },
  max_open_positions: { min: 1, max: 60 },
  min_cash_reserve_fraction: { min: 0, max: 0.5 },
  min_risk_reward_ratio: { min: 1, max: 5 },
  earnings_embargo_days: { min: 0, max: 10 },
};

const invested = () => state.positions.reduce((a, p) => a + p.qty * p.px, 0);
const equity = () => state.cash + invested();

// A year and a half of daily closes ending at today's equity; SPY on the same days.
const SERIES_DAYS = 540;
function series() {
  const r = rng(7);
  const days: number[] = [];
  const today = new Date();
  today.setUTCHours(21, 0, 0, 0);
  for (let i = SERIES_DAYS; i >= 1; i--) {
    const d = new Date(today.getTime() - i * DAY);
    if (d.getUTCDay() !== 0 && d.getUTCDay() !== 6) days.push(d.getTime());
  }
  const eq: number[] = [];
  const spy: number[] = [];
  let e = 100_000;
  let s = 520;
  for (let i = 0; i < days.length; i++) {
    const m = (r() - 0.48) * 0.018;
    s *= 1 + m;
    const shock = i > days.length * 0.62 && i < days.length * 0.7 ? -0.0025 : 0;
    e *= 1 + m * 0.7 + (r() - 0.46) * 0.008 + shock;
    eq.push(e);
    spy.push(s);
  }
  // Yesterday's close sits a little under today's equity, so the day change is not zero.
  const k = (equity() * 0.9963) / e;
  return { days, eq: eq.map((v) => v * k), spy };
}

function equityHistory() {
  const { days, eq } = series();
  let peak = -Infinity;
  const pts = days.map((t, i) => {
    peak = Math.max(peak, eq[i]);
    return { ts: iso(t), equity: +eq[i].toFixed(2), cash: state.cash, drawdown_fraction: +(eq[i] / peak - 1).toFixed(5) };
  });
  const now = equity();
  peak = Math.max(peak, now);
  pts.push({ ts: iso(Date.now() - 12_000), equity: +now.toFixed(2), cash: state.cash, drawdown_fraction: +(now / peak - 1).toFixed(5) });
  return pts;
}

function spyBars() {
  const { days, spy } = series();
  const r = rng(11);
  return days.map((t, i) => {
    const c = spy[i];
    const o = i ? spy[i - 1] : c;
    return { time: Math.floor(t / 1000), open: +o.toFixed(2), high: +(Math.max(o, c) * (1 + r() * 0.006)).toFixed(2), low: +(Math.min(o, c) * (1 - r() * 0.006)).toFixed(2), close: +c.toFixed(2), volume: Math.round(60e6 + r() * 30e6) };
  });
}

const AGENTS = ["technical_analyst", "portfolio_manager", "market_analyst", "fundamental_analyst", "sentiment_analyst"];
const SECTOR: Record<string, string> = { NVDA: "Tecnologia", MSFT: "Tecnologia", AMD: "Tecnologia", AAPL: "Tecnologia", META: "Tecnologia", LLY: "Sanità", UNH: "Sanità", JPM: "Finanza", GS: "Finanza", XOM: "Energia", CVX: "Energia", TSLA: "Consumi", COST: "Consumi" };

function closedTrades() {
  const r = rng(23);
  const names = Object.keys(SECTOR);
  const out: Record<string, unknown>[] = [];
  for (let i = 0; i < 26; i++) {
    const ticker = names[Math.floor(r() * names.length)];
    const entry = +(80 + r() * 600).toFixed(2);
    const riskPer = entry * (0.025 + r() * 0.02);
    const win = r() < 0.54;
    const rMult = win ? 0.6 + r() * 2.2 : -(0.4 + r() * 0.65);
    const exit = +(entry + rMult * riskPer).toFixed(2);
    const qty = Math.max(1, Math.round(9000 / entry));
    const closed = Date.now() - (6 + i * 17 + Math.floor(r() * 9)) * DAY;
    const dur = (2 + Math.floor(r() * 18)) * DAY + Math.floor(r() * 6) * 3_600_000;
    const reason = win ? (r() < 0.7 ? "tp" : "pm_sell") : r() < 0.8 ? "sl" : r() < 0.5 ? "expired" : "pm_sell";
    out.push({
      id: 60 - i,
      ticker,
      entry_order_id: 500 + i,
      exit_order_id: 600 + i,
      entry_price: entry,
      exit_price: exit,
      qty,
      exit_reason: reason,
      opened_ts: iso(closed - dur),
      closed_ts: iso(closed),
      r_multiple: +rMult.toFixed(2),
      duration_s: Math.round(dur / 1000),
      pnl: +((exit - entry) * qty).toFixed(2),
      proposed_by: i % 7 === 6 ? null : AGENTS[i % AGENTS.length],
    });
  }
  return out;
}

function openTrades() {
  return state.positions.map((p) => ({
    id: p.tradeId,
    ticker: p.ticker,
    entry_order_id: 400 + p.tradeId,
    exit_order_id: null,
    entry_price: p.avg,
    exit_price: null,
    qty: p.qty,
    exit_reason: null,
    opened_ts: iso(Date.now() - p.daysAgo * DAY),
    closed_ts: null,
    r_multiple: null,
    duration_s: null,
    pnl: null,
    proposed_by: p.agent,
  }));
}

const allTrades = () => [...openTrades(), ...state.closedExtra, ...closedTrades()];

function positions() {
  const eq = equity();
  return state.positions.map((p) => {
    const mv = p.qty * p.px;
    const upl = (p.px - p.avg) * p.qty;
    const risk = Math.max(0, (p.px - p.stop) * p.qty);
    return {
      ticker: p.ticker,
      side: "long",
      qty: p.qty,
      avg_entry_price: p.avg,
      current_price: p.px,
      market_value: +mv.toFixed(2),
      weight: +(mv / eq).toFixed(5),
      unrealized_pnl: +upl.toFixed(2),
      unrealized_pnl_fraction: +(upl / (p.avg * p.qty)).toFixed(5),
      stop_price: p.stop,
      target_price: p.target,
      open_risk: +risk.toFixed(2),
      open_risk_fraction: +(risk / eq).toFixed(5),
      sector: p.sector,
      opened_ts: iso(Date.now() - p.daysAgo * DAY),
      days_held: p.daysAgo,
      trade_id: p.tradeId,
      proposed_by: p.agent,
    };
  });
}

function bySector() {
  const eq = equity();
  const m = new Map<string, number>();
  for (const p of state.positions) m.set(p.sector, (m.get(p.sector) ?? 0) + p.qty * p.px);
  return [...m].map(([sector, value]) => ({ sector, value: +value.toFixed(2), weight: +(value / eq).toFixed(5), limit: state.limits.max_sector_fraction })).sort((a, b) => b.weight - a.weight);
}

function allocation() {
  const eq = equity();
  return {
    by_sector: bySector(),
    by_position: positions().map((p) => ({ ticker: p.ticker, value: p.market_value, weight: p.weight, limit: state.limits.max_position_fraction })).sort((a, b) => b.weight - a.weight),
    cash: { value: state.cash, weight: +(state.cash / eq).toFixed(5), min_reserve: state.limits.min_cash_reserve_fraction },
  };
}

function summary() {
  const hist = equityHistory();
  const eq = equity();
  const prev = hist[hist.length - 2].equity;
  return {
    ts: iso(Date.now() - 12_000),
    equity: +eq.toFixed(2),
    cash: state.cash,
    invested: +invested().toFixed(2),
    cash_reserve_fraction: +(state.cash / eq).toFixed(5),
    day_change: +(eq - prev).toFixed(2),
    day_change_fraction: +(eq / prev - 1).toFixed(5),
    unrealized_pnl: +state.positions.reduce((a, p) => a + (p.px - p.avg) * p.qty, 0).toFixed(2),
    realized_pnl_today: state.closedExtra.reduce((a, t) => a + Number(t.pnl ?? 0), 0),
    positions_count: state.positions.length,
    snapshot_age_s: 12,
    halted: state.halted,
  };
}

function periodStart(period: string): number | null {
  const now = new Date();
  const map: Record<string, () => number> = {
    "1D": () => now.getTime() - DAY,
    "1W": () => now.getTime() - 7 * DAY,
    "1M": () => new Date(now.getFullYear(), now.getMonth() - 1, now.getDate()).getTime(),
    "3M": () => new Date(now.getFullYear(), now.getMonth() - 3, now.getDate()).getTime(),
    YTD: () => new Date(now.getFullYear(), 0, 1).getTime(),
    "1Y": () => new Date(now.getFullYear() - 1, now.getMonth(), now.getDate()).getTime(),
  };
  return map[period]?.() ?? null;
}

const mean = (a: number[]) => a.reduce((x, y) => x + y, 0) / a.length;
const std = (a: number[]) => {
  const m = mean(a);
  return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / (a.length - 1));
};

function performance(period: string) {
  const start = periodStart(period);
  const pts = equityHistory().filter((p) => start === null || Date.parse(p.ts) >= start);
  const spy = spyBars().filter((b) => start === null || b.time * 1000 >= start);
  const rets = pts.slice(1).map((p, i) => p.equity / pts[i].equity - 1);
  const insufficient: { metric: string; reason: string; min_observations: number }[] = [];
  const MIN = 20;
  let peak = -Infinity;
  let maxDD = 0;
  for (const p of pts) {
    peak = Math.max(peak, p.equity);
    maxDD = Math.min(maxDD, p.equity / peak - 1);
  }
  const enoughRet = rets.length >= MIN;
  if (!enoughRet) for (const m of ["volatility_annualized", "sharpe", "sortino"]) insufficient.push({ metric: m, reason: `Servono almeno ${MIN} rendimenti giornalieri (ora ${rets.length}).`, min_observations: MIN });
  const vol = enoughRet ? std(rets) * Math.sqrt(252) : null;
  const downside = rets.filter((x) => x < 0);
  const dd = downside.length > 1 ? Math.sqrt(downside.reduce((a, x) => a + x * x, 0) / rets.length) * Math.sqrt(252) : null;
  const trades = allTrades().filter((t) => t.closed_ts && (start === null || Date.parse(String(t.closed_ts)) >= start));
  const pnls = trades.map((t) => Number(t.pnl));
  const MIN_T = 5;
  const enoughT = trades.length >= MIN_T;
  if (!enoughT) for (const m of ["win_rate", "profit_factor", "expectancy", "expectancy_r"]) insufficient.push({ metric: m, reason: `Servono almeno ${MIN_T} trade chiusi nel periodo (ora ${trades.length}).`, min_observations: MIN_T });
  const wins = pnls.filter((x) => x > 0);
  const losses = pnls.filter((x) => x < 0);
  let benchmark = null;
  if (spy.length >= 2) {
    const sr = spy.slice(1).map((b, i) => b.close / spy[i].close - 1);
    const n = Math.min(sr.length, rets.length);
    let beta = null;
    let corr = null;
    if (n >= MIN) {
      const a = rets.slice(-n);
      const b = sr.slice(-n);
      const ma = mean(a);
      const mb = mean(b);
      const cov = a.reduce((x, v, i) => x + (v - ma) * (b[i] - mb), 0) / (n - 1);
      beta = cov / std(b) ** 2;
      corr = cov / (std(a) * std(b));
    } else insufficient.push({ metric: "beta", reason: `Servono almeno ${MIN} giorni allineati con SPY.`, min_observations: MIN });
    benchmark = { ticker: "SPY", return_fraction: +(spy[spy.length - 1].close / spy[0].close - 1).toFixed(5), beta: beta === null ? null : +beta.toFixed(3), correlation: corr === null ? null : +corr.toFixed(3) };
  }
  const last = pts[pts.length - 1];
  return {
    period,
    from: pts[0]?.ts ?? null,
    to: last?.ts ?? null,
    observations: pts.length,
    return_fraction: pts.length >= 2 ? +(last.equity / pts[0].equity - 1).toFixed(5) : null,
    realized_pnl: +pnls.reduce((a, x) => a + x, 0).toFixed(2),
    unrealized_pnl: summary().unrealized_pnl,
    max_drawdown_fraction: pts.length >= 2 ? +maxDD.toFixed(5) : null,
    current_drawdown_fraction: pts.length >= 2 ? +(last.equity / peak - 1).toFixed(5) : null,
    volatility_annualized: vol === null ? null : +vol.toFixed(4),
    sharpe: vol ? +((mean(rets) * 252) / vol).toFixed(2) : null,
    sortino: enoughRet && dd ? +((mean(rets) * 252) / dd).toFixed(2) : null,
    win_rate: enoughT ? +(wins.length / trades.length).toFixed(4) : null,
    profit_factor: enoughT && losses.length ? +(wins.reduce((a, x) => a + x, 0) / Math.abs(losses.reduce((a, x) => a + x, 0))).toFixed(2) : null,
    expectancy: enoughT ? +mean(pnls).toFixed(2) : null,
    expectancy_r: enoughT ? +mean(trades.map((t) => Number(t.r_multiple ?? 0))).toFixed(2) : null,
    trades_closed: trades.length,
    benchmark,
    insufficient,
  };
}

function attribution(period: string) {
  const start = periodStart(period);
  const startEq = equityHistory().find((p) => start === null || Date.parse(p.ts) >= start)?.equity ?? equity();
  const trades = allTrades().filter((t) => t.closed_ts && (start === null || Date.parse(String(t.closed_ts)) >= start));
  const pos = new Map<string, number>();
  const sec = new Map<string, number>();
  const agent = new Map<string, { pnl: number; trades: number }>();
  const add = (ticker: string, pnl: number, who: string | null) => {
    pos.set(ticker, (pos.get(ticker) ?? 0) + pnl);
    const s = SECTOR[ticker] ?? "Altro";
    sec.set(s, (sec.get(s) ?? 0) + pnl);
    const k = who ?? "sconosciuto";
    const a = agent.get(k) ?? { pnl: 0, trades: 0 };
    agent.set(k, { pnl: a.pnl + pnl, trades: a.trades + 1 });
  };
  for (const t of trades) add(String(t.ticker), Number(t.pnl), (t.proposed_by as string | null) ?? null);
  for (const p of state.positions) add(p.ticker, (p.px - p.avg) * p.qty, p.agent);
  const frac = (v: number) => +(v / startEq).toFixed(5);
  return {
    by_position: [...pos].map(([ticker, pnl]) => ({ ticker, pnl: +pnl.toFixed(2), contribution_fraction: frac(pnl) })).sort((a, b) => b.pnl - a.pnl),
    by_sector: [...sec].map(([sector, pnl]) => ({ sector, pnl: +pnl.toFixed(2), contribution_fraction: frac(pnl) })).sort((a, b) => b.pnl - a.pnl),
    by_agent: [...agent].map(([a, v]) => ({ agent: a, pnl: +v.pnl.toFixed(2), contribution_fraction: frac(v.pnl), trades: v.trades })).sort((a, b) => b.pnl - a.pnl),
  };
}

function usage() {
  const eq = equity();
  const L = state.limits;
  const status = (cur: number | null, thr: number, min = false) => (cur === null ? "ok" : min ? (cur < thr ? "breach" : cur < thr * 1.25 ? "near" : "ok") : cur > thr + 1e-9 ? "breach" : cur >= thr * 0.8 ? "near" : "ok");
  const pos = positions();
  const top = [...pos].sort((a, b) => b.weight - a.weight)[0];
  const risky = [...pos].sort((a, b) => b.open_risk_fraction - a.open_risk_fraction)[0];
  const sec = bySector()[0];
  const rrs = state.positions.map((p) => ({ t: p.ticker, rr: (p.target - p.px) / Math.max(0.01, p.px - p.stop) }));
  const minRR = rrs.sort((a, b) => a.rr - b.rr)[0];
  const cash = state.cash / eq;
  return [
    { limit: "max_risk_per_trade_fraction", current: risky?.open_risk_fraction ?? null, threshold: L.max_risk_per_trade_fraction, status: status(risky?.open_risk_fraction ?? null, L.max_risk_per_trade_fraction), detail: risky ? `Rischio aperto più alto: ${risky.ticker}` : null },
    { limit: "max_position_fraction", current: top?.weight ?? null, threshold: L.max_position_fraction, status: status(top?.weight ?? null, L.max_position_fraction), detail: top ? `Posizione più pesante: ${top.ticker}` : null },
    { limit: "max_sector_fraction", current: sec?.weight ?? null, threshold: L.max_sector_fraction, status: status(sec?.weight ?? null, L.max_sector_fraction), detail: sec ? `Settore più esposto: ${sec.sector}` : null },
    { limit: "max_open_positions", current: pos.length, threshold: L.max_open_positions, status: status(pos.length, L.max_open_positions), detail: null },
    { limit: "min_cash_reserve_fraction", current: +cash.toFixed(5), threshold: L.min_cash_reserve_fraction, status: status(cash, L.min_cash_reserve_fraction, true), detail: null },
    { limit: "min_risk_reward_ratio", current: minRR ? +minRR.rr.toFixed(2) : null, threshold: L.min_risk_reward_ratio, status: status(minRR?.rr ?? null, L.min_risk_reward_ratio, true), detail: minRR ? `R:R residuo più basso: ${minRR.t}` : null },
    { limit: "earnings_embargo_days", current: null, threshold: L.earnings_embargo_days, status: "ok", detail: "Nessuna trimestrale entro la finestra" },
  ];
}

function riskLimits() {
  return { version: state.version, updated_ts: state.updatedTs, updated_by: state.updatedBy, limits: state.limits, bounds: BOUNDS, usage: usage() };
}

const pct = (v: number) => `${(v * 100).toFixed(2).replace(".", ",")}%`;

function closePosition(p: Record<string, unknown>) {
  const pos = state.positions.find((x) => x.ticker === String(p.ticker).toUpperCase());
  if (!pos) return { ok: false, data: {}, reasons: [`Nessuna posizione aperta su ${p.ticker}`] };
  if (state.halted) return { ok: false, data: {}, reasons: ["Halt attivo: nessun ordine può partire"] };
  const qty = p.qty === null || p.qty === undefined ? pos.qty : Number(p.qty);
  if (!(qty > 0) || qty > pos.qty) return { ok: false, data: {}, reasons: [`Quantità non valida: tra 1 e ${pos.qty}`] };
  const price = p.order_type === "limit" && p.limit_price ? Number(p.limit_price) : pos.px;
  // Field names as the Runtime's preview_close returns them (execution/position_exits.py).
  const preview = { ticker: pos.ticker, qty, qty_remaining_after: pos.qty - qty, order_type: p.order_type, limit_price: p.limit_price ?? null, reference_price: price, estimated_value: +(qty * price).toFixed(2), estimated_realized_pnl: +((price - pos.avg) * qty).toFixed(2), closes_position: qty >= pos.qty, risk_gate: { allowed: true, reasons: [] as string[] } };
  if (p.dry_run) return { ok: true, data: preview, reasons: [] };
  state.cash += qty * price;
  state.closedExtra.unshift({ id: 900 + state.closedExtra.length, ticker: pos.ticker, entry_order_id: 400 + pos.tradeId, exit_order_id: 950, entry_price: pos.avg, exit_price: price, qty, exit_reason: "pm_sell", opened_ts: iso(Date.now() - pos.daysAgo * DAY), closed_ts: iso(Date.now()), r_multiple: +((price - pos.avg) / (pos.avg - pos.stop)).toFixed(2), duration_s: pos.daysAgo * 86400, pnl: preview.estimated_realized_pnl, proposed_by: pos.agent });
  pos.qty -= qty;
  if (pos.qty === 0) state.positions = state.positions.filter((x) => x !== pos);
  return { ok: true, data: { ...preview, order: { order_id: 990, ticker: pos.ticker, side: "sell", qty, order_type: p.order_type, status: "submitted" } }, reasons: [] };
}

function modifyExit(p: Record<string, unknown>) {
  const pos = state.positions.find((x) => x.ticker === String(p.ticker).toUpperCase());
  if (!pos) return { ok: false, data: {}, reasons: [`Nessuna posizione aperta su ${p.ticker}`] };
  const stop = p.stop_price === null || p.stop_price === undefined ? pos.stop : Number(p.stop_price);
  const target = p.target_price === null || p.target_price === undefined ? pos.target : Number(p.target_price);
  const eq = equity();
  const before = Math.max(0, (pos.px - pos.stop) * pos.qty);
  const after = Math.max(0, (pos.px - stop) * pos.qty);
  const reasons: string[] = [];
  if (stop >= pos.px) reasons.push(`Lo stop deve stare sotto il prezzo corrente (${pos.px})`);
  if (target <= pos.px) reasons.push(`Il target deve stare sopra il prezzo corrente (${pos.px})`);
  if (stop < pos.stop && after / eq > state.limits.max_risk_per_trade_fraction) reasons.push(`Rischio per trade ${pct(after / eq)} oltre il limite ${pct(state.limits.max_risk_per_trade_fraction)}`);
  // Field names as the Runtime's preview_modify returns them.
  const preview = { ticker: pos.ticker, stop_price: stop, target_price: target, previous_stop_price: pos.stop, previous_target_price: pos.target, widening_stop: stop < pos.stop, tightening_stop: stop > pos.stop, open_risk_before: +before.toFixed(2), open_risk: +after.toFixed(2), open_risk_fraction: +(after / eq).toFixed(5), risk_gate: { allowed: reasons.length === 0, reasons } };
  if (p.dry_run) return { ok: true, data: preview, reasons: [] };
  if (reasons.length) return { ok: false, data: preview, reasons };
  pos.stop = stop;
  pos.target = target;
  return { ok: true, data: preview, reasons: [] };
}

function updateLimits(p: Record<string, unknown>) {
  const next = (p.limits ?? {}) as Record<string, number>;
  const reason = String(p.reason ?? "").trim();
  const reasons: string[] = [];
  if (!reason) reasons.push("Il motivo è obbligatorio");
  for (const [k, v] of Object.entries(next)) {
    const b = BOUNDS[k];
    if (!b) reasons.push(`Limite sconosciuto: ${k}`);
    else if (!(v >= b.min && v <= b.max)) reasons.push(`${k}: ${v} fuori dall'intervallo ${b.min}–${b.max}`);
  }
  if (reasons.length) return { ok: false, data: {}, reasons };
  const before: Record<string, number> = {};
  for (const k of Object.keys(next)) before[k] = state.limits[k];
  state.limits = { ...state.limits, ...next };
  state.version += 1;
  state.updatedTs = iso(Date.now());
  state.updatedBy = "cockpit";
  state.history.unshift({ version: state.version, ts: state.updatedTs, actor: "cockpit", reason, before, after: next });
  return { ok: true, data: riskLimits(), reasons: [] };
}

function readBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      try {
        resolve(JSON.parse(raw || "{}"));
      } catch {
        resolve({});
      }
    });
  });
}

function send(res: ServerResponse, body: unknown) {
  res.setHeader("Content-Type", "application/json");
  res.setHeader("X-Dev-Fixture", "portfolio");
  res.end(JSON.stringify(body));
}

export function portfolioFixtures(): Plugin {
  return {
    name: "cockpit-portfolio-fixtures",
    apply: "serve",
    configureServer(server) {
      server.config.logger.info("  ⚠ Portafoglio: fixture di sviluppo attive per le letture e i comandi del contratto (COCKPIT_PORTFOLIO_FIXTURES=1)");
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url ?? "/", "http://dev");
        const read = url.pathname.match(/^\/v1\/read\/([a-z_]+)$/)?.[1];
        const period = url.searchParams.get("period") ?? "1M";
        if (read) {
          if (read === "bars" && !(url.searchParams.get("ticker") === "SPY" && url.searchParams.get("timeframe") === "1d")) return next();
          const reads: Record<string, () => unknown> = {
            portfolio_summary: summary,
            portfolio: () => ({ ts: summary().ts, equity: +equity().toFixed(2), cash: state.cash, positions: state.positions.map((p) => ({ symbol: p.ticker, qty: p.qty, avg_entry_price: p.avg, current_price: p.px, market_value: +(p.qty * p.px).toFixed(2), unrealized_pl: +((p.px - p.avg) * p.qty).toFixed(2) })) }),
            positions,
            allocation,
            performance: () => performance(period),
            attribution: () => attribution(period),
            risk_limits: riskLimits,
            risk_limits_history: () => state.history,
            equity_history: equityHistory,
            trades: allTrades,
            bars: spyBars,
          };
          const fn = reads[read];
          return fn ? send(res, fn()) : next();
        }
        const cmd = url.pathname.match(/^\/v1\/commands\/(close_position|modify_exit|update_risk_limits)$/)?.[1];
        if (cmd && req.method === "POST") {
          const body = await readBody(req);
          return send(res, cmd === "close_position" ? closePosition(body) : cmd === "modify_exit" ? modifyExit(body) : updateLimits(body));
        }
        next();
      });
    },
  };
}
