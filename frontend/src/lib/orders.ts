import { toNum } from "./format";
import type { Order } from "./runtime/types";

/**
 * The Runtime's OrderDTO reads qty/limit_price/stop_loss from keys the draft does not use
 * (the draft stores quantity/entry/stop): read the draft first, the DTO fields as fallback.
 */
export function orderFigures(o: Order) {
  const d = o.draft_json ?? {};
  const qty = toNum(d.quantity) ?? (o.qty || null);
  const entry = toNum(d.entry) ?? o.limit_price;
  const stop = toNum(d.stop) ?? o.stop_loss;
  const tp = toNum(d.take_profit) ?? o.take_profit;
  const rr =
    toNum(d.risk_reward) ??
    (entry !== null && stop !== null && tp !== null && entry !== stop ? Math.abs(tp - entry) / Math.abs(entry - stop) : null);
  const risk = toNum(d.risk_amount) ?? (entry !== null && stop !== null && qty !== null ? Math.abs(entry - stop) * qty : null);
  const notional = toNum(d.notional) ?? (entry !== null && qty !== null ? entry * qty : null);
  return { qty, entry, stop, tp, rr, risk, notional };
}

export type OrderBucket = "pending" | "open" | "done";

const OPEN = new Set(["submitted", "open", "queued", "accepted", "new", "partially_filled", "deferred", "pending_new"]);

export function orderBucket(o: Order): OrderBucket {
  if (o.approval_status === "pending" && o.status === "pending") return "pending";
  if (OPEN.has(o.status) || o.status === "pending") return "open";
  return "done";
}

export const STATUS_LABEL: Record<string, string> = {
  pending: "In attesa",
  submitted: "Inviato",
  open: "Aperto",
  queued: "In coda",
  deferred: "Rinviato",
  filled: "Eseguito",
  partially_filled: "Parziale",
  cancelled: "Annullato",
  canceled: "Annullato",
  rejected: "Rifiutato",
  expired: "Scaduto",
};

export const EXIT_LABEL: Record<string, string> = {
  tp: "Take profit",
  sl: "Stop loss",
  pm_sell: "Vendita PM",
  expired: "Scaduto",
  reconciled_unknown: "Riconciliato",
};

/** Risk Gate limits (PRODUCT.md): shown wherever an order can be approved. */
export const RISK_LIMITS = {
  minRR: 1.5,
  tradeRiskPct: 1,
  positionPct: 10,
  sectorPct: 30,
  maxPositions: 30,
  cashReservePct: 5,
  earningsEmbargoDays: 2,
};
