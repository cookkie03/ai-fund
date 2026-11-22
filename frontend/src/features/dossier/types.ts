// Wire types of the ticker-agent reads. Field names are the binding contract in
// .scratch/ticker-agents/handoff-backend.md ("Contratto"), copied verbatim: do not rename.
// Fractions are 0..1, timestamps ISO UTC. They land with the `ticker-agents-backend` branch;
// until then the adapters in ./api.ts answer `unavailable` and name the endpoint they wait for.

export type DossierStatus = "idle" | "analyzing" | "proposed" | "approved" | "declined" | "monitoring";
export type FactStatus = "active" | "stale" | "superseded";
export type ProposalStatus = "pending" | "accepted" | "deferred" | "rejected" | "asked";

export type DossierIdentity = {
  name: string | null;
  sector: string | null;
  industry: string | null;
  market_cap: number | null;
  currency: string | null;
  current_price: number | null;
  as_of: string | null;
};

export type DossierPortfolio = {
  invested: boolean;
  qty: number | null;
  position_weight: number | null;
  avg_entry_price: number | null;
  unrealized_pnl: number | null;
  sector_exposure: number | null;
  cash_fraction: number | null;
};

/** One specialist contribution. `agent` is the author id (e.g. `technical_analyst`). */
export type DeskFact = {
  agent: string;
  section: string;
  text: string;
  ts: string;
  reference_date: string | null;
  confidence: number | null;
  status: FactStatus;
};

export type Catalyst = { text: string; date: string | null };

export type Thesis = {
  direction: string;
  conviction: number | null;
  pro: string[];
  contro: string[];
  time_horizon: string | null;
  catalysts: Catalyst[];
  next_check_date: string | null;
  author: string;
  ts: string;
};

export type DossierProposal = {
  id: number;
  status: ProposalStatus | string;
  k_entry: number | null;
  k_stop: number | null;
  k_tp: number | null;
  entry_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  sizing_fraction: number | null;
  risk_reward: number | null;
  submitted_ts: string | null;
};

export type Guardrail = { rule: string; ok: boolean; detail: string | null };

export type RiskVerdict = { verdict: string; rationale: string | null; guardrails: Guardrail[] };

export type Decision = { ts: string; actor: string; action: string; reason: string | null; cycle_id: number | null };

export type Lesson = { ts: string; text: string; exit_reason: string | null };

export type DossierNote = { id: number | string; author: string; text: string; ts: string };

/** `GET /v1/read/dossier?ticker=` */
export type Dossier = {
  ticker: string;
  version: number;
  updated_ts: string | null;
  updated_by: string | null;
  status: DossierStatus | string;
  identity: DossierIdentity;
  portfolio: DossierPortfolio;
  desks: DeskFact[];
  thesis: Thesis | null;
  proposal: DossierProposal | null;
  risk: RiskVerdict | null;
  decisions: Decision[];
  lessons: Lesson[];
  notes: DossierNote[];
  stale_count: number;
};

/** `GET /v1/read/dossier_history?ticker=&limit=` */
export type DossierVersion = { version: number; ts: string; author: string; sections_changed: string[] };

/** `GET /v1/read/proposals?status=&ticker=&limit=` */
export type Proposal = {
  id: number;
  ticker: string;
  agent: string;
  status: ProposalStatus | string;
  direction: string | null;
  conviction: number | null;
  sizing_fraction: number | null;
  risk_reward: number | null;
  submitted_ts: string | null;
  decided_ts: string | null;
  decided_by: string | null;
  reason: string | null;
  cycle_id: number | null;
};

/** `GET /v1/read/dossiers?limit=`: one summary row per ticker, for the Ufficio desk and lists. */
export type DossierSummary = {
  ticker: string;
  status: DossierStatus | string;
  direction: string | null;
  conviction: number | null;
  proposal_status: ProposalStatus | string | null;
  updated_ts: string | null;
  stale_count: number;
  invested: boolean;
};

/** What a read returned: the Runtime answered, the endpoint is not exposed yet, or there is no dossier for the ticker. */
export type Read<T> =
  | { state: "ok"; data: T }
  | { state: "unavailable"; endpoint: string }
  | { state: "missing" };

export type DecideAction = "accept" | "defer" | "reject" | "ask";
