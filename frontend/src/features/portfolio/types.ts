// Contracts the Portafoglio reads and writes. Field names are fixed by
// .scratch/cockpit/handoff-backend-portafoglio.md (binding): amounts in account currency, percentages as
// fractions (0.12 = 12%), timestamps ISO UTC. Do not rename or add variants here: the backend uses these names.

export type { Sourced } from "@/features/office/types";

/** 1. `GET /v1/read/portfolio_summary` */
export type PortfolioSummary = {
  ts: string;
  equity: number;
  cash: number;
  invested: number;
  cash_reserve_fraction: number | null;
  day_change: number | null;
  day_change_fraction: number | null;
  unrealized_pnl: number;
  realized_pnl_today: number | null;
  positions_count: number;
  snapshot_age_s: number | null;
  halted: boolean;
};

/** 2. One row of `GET /v1/read/positions` */
export type PortfolioPosition = {
  ticker: string;
  side: "long" | "short" | string;
  qty: number;
  avg_entry_price: number;
  current_price: number | null;
  market_value: number | null;
  weight: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_fraction: number | null;
  stop_price: number | null;
  target_price: number | null;
  /** Loss down to the stop. */
  open_risk: number | null;
  open_risk_fraction: number | null;
  sector: string | null;
  opened_ts: string | null;
  days_held: number | null;
  trade_id: number | null;
  /** Agent that proposed the trade; null when unknown. */
  proposed_by: string | null;
};

/** 3. `GET /v1/read/allocation` */
export type AllocationRow = { value: number; weight: number; limit: number | null };
export type Allocation = {
  by_sector: (AllocationRow & { sector: string })[];
  by_position: (AllocationRow & { ticker: string })[];
  cash: { value: number; weight: number; min_reserve: number | null };
};

export type Period = "1D" | "1W" | "1M" | "3M" | "YTD" | "1Y" | "ALL";
export const PERIODS: Period[] = ["1D", "1W", "1M", "3M", "YTD", "1Y", "ALL"];
export const PERIOD_LABEL: Record<Period, string> = { "1D": "1G", "1W": "1S", "1M": "1M", "3M": "3M", YTD: "YTD", "1Y": "1A", ALL: "Tutto" };

export type Insufficient = { metric: string; reason: string; min_observations: number | null };

/** 4. `GET /v1/read/performance?period=&benchmark=SPY` */
export type Performance = {
  period: Period;
  from: string | null;
  to: string | null;
  observations: number;
  return_fraction: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  max_drawdown_fraction: number | null;
  current_drawdown_fraction: number | null;
  volatility_annualized: number | null;
  sharpe: number | null;
  sortino: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  expectancy: number | null;
  expectancy_r: number | null;
  trades_closed: number;
  benchmark: { ticker: string; return_fraction: number | null; beta: number | null; correlation: number | null } | null;
  insufficient: Insufficient[];
};

/** 5. `GET /v1/read/attribution?period=` */
export type Attribution = {
  by_position: { ticker: string; pnl: number; contribution_fraction: number }[];
  by_sector: { sector: string; pnl: number; contribution_fraction: number }[];
  by_agent: { agent: string; pnl: number; contribution_fraction: number; trades: number }[];
};

/** 6. One row of `GET /v1/read/trades`, with the fields the backend adds for the Portafoglio. */
export type PortfolioTrade = {
  id: number;
  ticker: string;
  entry_order_id: number;
  exit_order_id: number | null;
  entry_price: number;
  exit_price: number | null;
  qty: number;
  exit_reason: string | null;
  opened_ts: string;
  closed_ts: string | null;
  r_multiple: number | null;
  duration_s: number | null;
  pnl: number | null;
  proposed_by: string | null;
};

export type LimitName =
  | "max_risk_per_trade_fraction"
  | "max_position_fraction"
  | "max_sector_fraction"
  | "max_open_positions"
  | "min_cash_reserve_fraction"
  | "min_risk_reward_ratio"
  | "earnings_embargo_days";

export const LIMIT_NAMES: LimitName[] = [
  "max_risk_per_trade_fraction",
  "max_position_fraction",
  "max_sector_fraction",
  "max_open_positions",
  "min_cash_reserve_fraction",
  "min_risk_reward_ratio",
  "earnings_embargo_days",
];

export type RiskLimits = Record<LimitName, number>;
export type LimitStatus = "ok" | "near" | "breach";
export type LimitUsage = { limit: LimitName | string; current: number | null; threshold: number; status: LimitStatus; detail: string | null };

/** 7. `GET /v1/read/risk_limits` */
export type RiskLimitsRead = {
  version: number;
  updated_ts: string | null;
  updated_by: string | null;
  limits: RiskLimits;
  bounds: Partial<Record<LimitName, { min: number; max: number }>>;
  usage: LimitUsage[];
};

/** 8. One row of `GET /v1/read/risk_limits_history?limit=` */
export type RiskLimitsChange = {
  version: number;
  ts: string;
  actor: string;
  reason: string;
  before: Partial<RiskLimits>;
  after: Partial<RiskLimits>;
};

/** 9. `equity_history` point; `drawdown_fraction` arrives with the backend. */
export type EquityPointDD = { ts: string; equity: number; cash: number; drawdown_fraction: number | null };

// Commands. Response `{ok, data, reasons}`. The `dry_run` data fields are not fixed by the handoff: these names
// were proposed to the backend session on 2026-11-22 (see .scratch/cockpit/wiki-notes-portafoglio-frontend.md).

export type GateOutcome = { ok: boolean; reasons: string[] };

export type ClosePositionPayload = {
  ticker: string;
  qty: number | null;
  order_type: "market" | "limit";
  limit_price: number | null;
  dry_run?: boolean;
  confirm: true;
};

export type ClosePreview = {
  ticker: string;
  qty: number | null;
  remaining_qty: number | null;
  est_price: number | null;
  est_value: number | null;
  realized_pnl: number | null;
  gate: GateOutcome | null;
};

export type ModifyExitPayload = { ticker: string; stop_price: number | null; target_price: number | null; dry_run?: boolean; confirm: true };

export type ExitPreview = {
  ticker: string;
  qty: number | null;
  stop_price_before: number | null;
  stop_price: number | null;
  target_price_before: number | null;
  target_price: number | null;
  open_risk_before: number | null;
  open_risk: number | null;
  open_risk_fraction: number | null;
  gate: GateOutcome | null;
};

export type UpdateRiskLimitsPayload = { limits: Partial<RiskLimits>; reason: string; confirm: true };
