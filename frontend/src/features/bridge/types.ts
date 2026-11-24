// Wire types of the Bridge agent and the Assistente's reads. Field names are exactly the binding contract
// in .scratch/assistente/handoff-backend.md. Fractions stay fractions, timestamps ISO UTC.

export type RefType = "ticker" | "order" | "position" | "proposal" | "cycle" | "agent" | "trade";

export type MessageRef = { type: RefType | string; id: string; label: string | null };

/** The page Luca is on when he writes: lets the Bridge read "this" without asking. */
export type BridgeContext = { page: string; ticker: string | null; ref: { type: string; id: string } | null };

export type ActionStatus = "pending" | "confirmed" | "dismissed" | "executed" | "failed";

export type ActionPreview = { ok: boolean; reasons: string[]; detail: Record<string, unknown> | null };

export type BridgeAction = {
  id: number;
  command: string;
  payload: Record<string, unknown>;
  summary: string;
  capital: boolean;
  status: ActionStatus;
  preview: ActionPreview | null;
  result_reasons: string[];
  decided_ts: string | null;
  decided_by: string | null;
  /** Only on `GET /v1/read/bridge_actions`. */
  conversation_id: number | null;
};

export type MessageKind = "text" | "agent_relay" | "action" | "error";

export type BridgeMessage = {
  id: number;
  conversation_id: number;
  /** "luca", "bridge" or an agent id (agent_relay). */
  author: string;
  kind: MessageKind;
  text: string;
  ts: string;
  context: BridgeContext | null;
  refs: MessageRef[];
  action: BridgeAction | null;
};

export type TurnStatus = "idle" | "thinking";

export type ConversationSummary = {
  id: number;
  title: string;
  created_ts: string;
  updated_ts: string;
  message_count: number;
  status: TurnStatus;
  archived: boolean;
  last_message: { author: string; text: string; ts: string } | null;
  pending_actions: number;
};

export type Conversation = {
  id: number;
  title: string;
  created_ts: string;
  updated_ts: string;
  status: TurnStatus;
  archived: boolean;
  messages: BridgeMessage[];
};

export type BriefingItemType =
  | "trade"
  | "order_pending"
  | "proposal_pending"
  | "proposal_decided"
  | "alert"
  | "halt"
  | "resume"
  | "dossier"
  | "agent_error"
  | "risk_limits";

export type Severity = "info" | "attention" | "critical";

export type BriefingItem = {
  id: string;
  type: BriefingItemType | string;
  ts: string;
  title: string;
  detail: string | null;
  ticker: string | null;
  ref: { type: string; id: string } | null;
  severity: Severity;
};

export type Briefing = {
  since: string;
  generated_ts: string;
  summary_text: string | null;
  summary_ts: string | null;
  portfolio: { value: number; change: number | null; change_fraction: number | null } | null;
  counts: { trades: number; orders_pending: number; proposals_pending: number; proposals_decided: number; alerts: number; agent_errors: number };
  items: BriefingItem[];
};

/** A Bridge read: the data, or the endpoint the Runtime does not expose yet. */
export type BridgeRead<T> = { state: "ok"; data: T } | { state: "unavailable"; endpoint: string } | { state: "missing" };

/** Live turn state from `bridge.status` events, per conversation. */
export type LiveTurn = { status: "thinking" | "tool" | "idle"; tool: string | null; at: number };
