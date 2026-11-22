import { isNotExposed } from "@/features/office/api";
import { RuntimeError, type RuntimeClient } from "@/lib/runtime/client";
import type {
  DeskFact,
  Dossier,
  DossierProposal,
  DossierSummary,
  DossierVersion,
  FactStatus,
  Proposal,
  Read,
  RiskVerdict,
  Thesis,
} from "./types";

// Adapters for the ticker-agent reads. They read exactly the contract's field names
// (.scratch/ticker-agents/handoff-backend.md) and only coerce types: no aliases, no guessed names.
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
const factStatus = (v: unknown): FactStatus => (v === "stale" || v === "superseded" ? v : "active");

function desk(r: Row): DeskFact {
  return {
    agent: str(r.agent) ?? "",
    section: str(r.section) ?? "",
    text: str(r.text) ?? "",
    ts: str(r.ts) ?? "",
    reference_date: str(r.reference_date),
    confidence: num(r.confidence),
    status: factStatus(r.status),
  };
}

function thesis(v: unknown): Thesis | null {
  const r = obj(v);
  if (!r) return null;
  return {
    direction: str(r.direction) ?? "",
    conviction: num(r.conviction),
    pro: strs(r.pro),
    contro: strs(r.contro),
    time_horizon: str(r.time_horizon),
    catalysts: arr(r.catalysts).map((c) => ({ text: str(c.text) ?? "", date: str(c.date) })),
    next_check_date: str(r.next_check_date),
    author: str(r.author) ?? "",
    ts: str(r.ts) ?? "",
  };
}

function proposal(v: unknown): DossierProposal | null {
  const r = obj(v);
  if (!r || num(r.id) === null) return null;
  return {
    id: num(r.id)!,
    status: str(r.status) ?? "pending",
    k_entry: num(r.k_entry),
    k_stop: num(r.k_stop),
    k_tp: num(r.k_tp),
    entry_price: num(r.entry_price),
    stop_price: num(r.stop_price),
    target_price: num(r.target_price),
    sizing_fraction: num(r.sizing_fraction),
    risk_reward: num(r.risk_reward),
    submitted_ts: str(r.submitted_ts),
  };
}

function risk(v: unknown): RiskVerdict | null {
  const r = obj(v);
  if (!r) return null;
  return {
    verdict: str(r.verdict) ?? "",
    rationale: str(r.rationale),
    guardrails: arr(r.guardrails).map((g) => ({ rule: str(g.rule) ?? "", ok: g.ok === true, detail: str(g.detail) })),
  };
}

export function normalizeDossier(raw: unknown, ticker: string): Dossier | null {
  const r = obj(raw);
  if (!r) return null;
  const id = obj(r.identity) ?? {};
  const pf = obj(r.portfolio) ?? {};
  return {
    ticker: str(r.ticker) ?? ticker,
    version: num(r.version) ?? 0,
    updated_ts: str(r.updated_ts),
    updated_by: str(r.updated_by),
    status: str(r.status) ?? "idle",
    identity: {
      name: str(id.name),
      sector: str(id.sector),
      industry: str(id.industry),
      market_cap: num(id.market_cap),
      currency: str(id.currency),
      current_price: num(id.current_price),
      as_of: str(id.as_of),
    },
    portfolio: {
      invested: pf.invested === true,
      qty: num(pf.qty),
      position_weight: num(pf.position_weight),
      avg_entry_price: num(pf.avg_entry_price),
      unrealized_pnl: num(pf.unrealized_pnl),
      sector_exposure: num(pf.sector_exposure),
      cash_fraction: num(pf.cash_fraction),
    },
    desks: arr(r.desks).map(desk),
    thesis: thesis(r.thesis),
    proposal: proposal(r.proposal),
    risk: risk(r.risk),
    decisions: arr(r.decisions).map((d) => ({ ts: str(d.ts) ?? "", actor: str(d.actor) ?? "", action: str(d.action) ?? "", reason: str(d.reason), cycle_id: num(d.cycle_id) })),
    lessons: arr(r.lessons).map((l) => ({ ts: str(l.ts) ?? "", text: str(l.text) ?? "", exit_reason: str(l.exit_reason) })),
    notes: arr(r.notes).map((n) => ({ id: str(n.id) ?? "", author: str(n.author) ?? "", text: str(n.text) ?? "", ts: str(n.ts) ?? "" })),
    stale_count: num(r.stale_count) ?? 0,
  };
}

export function normalizeProposal(r: Row): Proposal {
  return {
    id: num(r.id) ?? 0,
    ticker: str(r.ticker) ?? "",
    agent: str(r.agent) ?? "",
    status: str(r.status) ?? "pending",
    direction: str(r.direction),
    conviction: num(r.conviction),
    sizing_fraction: num(r.sizing_fraction),
    risk_reward: num(r.risk_reward),
    submitted_ts: str(r.submitted_ts),
    decided_ts: str(r.decided_ts),
    decided_by: str(r.decided_by),
    reason: str(r.reason),
    cycle_id: num(r.cycle_id),
  };
}

function summary(r: Row): DossierSummary {
  return {
    ticker: str(r.ticker) ?? "",
    status: str(r.status) ?? "idle",
    direction: str(r.direction),
    conviction: num(r.conviction),
    proposal_status: str(r.proposal_status),
    updated_ts: str(r.updated_ts),
    stale_count: num(r.stale_count) ?? 0,
    invested: r.invested === true,
  };
}

/** A 404 that is not "endpoint not found" (or a null body) means: no dossier for this ticker yet. */
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

export const ENDPOINT = {
  dossier: "GET /v1/read/dossier",
  history: "GET /v1/read/dossier_history",
  proposals: "GET /v1/read/proposals",
  dossiers: "GET /v1/read/dossiers",
} as const;

export function fetchDossier(client: RuntimeClient, ticker: string): Promise<Read<Dossier>> {
  return guarded(ENDPOINT.dossier, async () => normalizeDossier(await client.read<unknown>("dossier", { ticker }), ticker));
}

export function fetchDossierHistory(client: RuntimeClient, ticker: string, limit = 30): Promise<Read<DossierVersion[]>> {
  return guarded(ENDPOINT.history, async () =>
    arr(await client.read<unknown>("dossier_history", { ticker, limit })).map((v) => ({
      version: num(v.version) ?? 0,
      ts: str(v.ts) ?? "",
      author: str(v.author) ?? "",
      sections_changed: strs(v.sections_changed),
    })),
  );
}

export function fetchProposals(client: RuntimeClient, params: { status?: string; ticker?: string; limit?: number }): Promise<Read<Proposal[]>> {
  return guarded(ENDPOINT.proposals, async () => arr(await client.read<unknown>("proposals", { limit: 100, ...params })).map(normalizeProposal));
}

export function fetchDossiers(client: RuntimeClient, limit = 200): Promise<Read<DossierSummary[]>> {
  return guarded(ENDPOINT.dossiers, async () => arr(await client.read<unknown>("dossiers", { limit })).map(summary));
}
