// Wire types of the Runtime `/v1` API (docs/dashboard.md). Field names mirror the Python DTOs.

export type Health = {
  account_label: string;
  runtime_version: string;
  halted: boolean;
  broker_stream_connected: boolean;
  broker_configured: boolean;
  next_scheduler_due_ts: string | null;
  db_size_bytes: number;
  last_event_id: number;
};

export type Position = {
  symbol?: string;
  ticker?: string;
  qty?: number | string;
  avg_entry_price?: number | string;
  current_price?: number | string;
  market_value?: number | string;
  unrealized_pl?: number | string;
};

export type PortfolioSnapshot = {
  ts: string;
  equity: number;
  cash: number;
  positions: Position[];
};

export type EquityPoint = { ts: string; equity: number; cash: number };

export type OrderDraft = {
  symbol?: string;
  side?: string;
  entry?: string | number;
  stop?: string | number | null;
  take_profit?: string | number | null;
  quantity?: string | number;
  risk_reward?: string | number | null;
  risk_amount?: string | number | null;
  notional?: string | number;
};

export type OrderEvent = {
  id: number;
  order_id: number;
  ts: string;
  event: string;
  detail: Record<string, unknown>;
};

export type Order = {
  id: number;
  ticker: string;
  side: string;
  qty: number;
  order_type: string;
  limit_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  client_order_id: string;
  broker_order_id: string | null;
  status: string;
  approval_status: "auto" | "pending" | "approved" | "rejected" | "expired" | string;
  draft_hash: string | null;
  draft_json: OrderDraft;
  rejection_reason: string | null;
  created_ts: string;
  updated_ts: string | null;
  events: OrderEvent[];
};

export type Trade = {
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
};

export type Cycle = {
  id: number;
  ticker: string;
  status: string;
  opened_ts: string;
  closed_ts: string | null;
  outcome: string | null;
  budget_used: Record<string, unknown>;
  messages: Message[];
};

export type Message = {
  id: number;
  chat_id: number;
  author: string;
  ts: string;
  text: string;
  kind: string;
  cycle_id: number | null;
};

export type WatchlistItem = {
  ticker: string;
  added_by: string;
  added_ts: string;
  note: string | null;
};

export type InboxItem = { id: number; ts: string; kind: string; text: string; read: boolean };

export type Bar = { time: number; open: number; high: number; low: number; close: number; volume: number };

export type IndicatorsResponse = {
  ticker: string;
  timeframe: string;
  series: number[];
  indicators: Record<string, (number | null)[]>;
};

export type AnnotationPoint = { time: number; price: number };

export type RuntimeDrawing = {
  type: string;
  points: AnnotationPoint[];
  text?: string;
  style?: Record<string, unknown>;
  [key: string]: unknown;
};

export type Annotation = {
  id: string;
  ticker: string;
  timeframe: string | null;
  author: string;
  created_at: string;
  updated_at: string;
  status: "active" | "struck" | string;
  struck_by: string | null;
  struck_at: string | null;
  drawing: RuntimeDrawing;
};

export type Suggestion = { direction: "buy" | "sell" | "hold" | string; conviction: number };

export type TickerState = {
  ticker?: string;
  analyses?: Record<string, string>;
  suggestions?: Record<string, Suggestion>;
  coefficients?: Record<string, number>;
  draft?: OrderDraft | null;
  decision?: { action: string; reason: string; decided_ts: string; status: string } | null;
};

export type CommandResult<T = Record<string, unknown>> = { ok: boolean; data: T; reasons: string[] };

export type RuntimeEvent = { id: number; type: string; data: Record<string, unknown> };

export type CommandName =
  | "enqueue_task"
  | "say"
  | "add_watchlist"
  | "remove_watchlist"
  | "upsert_annotation"
  | "strike_annotation"
  | "approve_order"
  | "reject_order"
  | "halt"
  | "resume"
  | "reconcile_broker"
  | "refresh_data"
  | "mark_inbox_read"
  | "add_dossier_note"
  | "decide_proposal"
  | "forward_news"
  | "add_news_source"
  | "set_news_source_enabled"
  | "remove_news_source"
  | "refresh_news"
  | "bridge_say"
  | "bridge_rename_conversation"
  | "bridge_archive_conversation"
  | "bridge_stop"
  | "bridge_action_decide"
  | "mark_briefing_seen";

export type CommandPayloads = {
  enqueue_task: { agent: string; ticker: string; reason: string; when_ts?: string };
  say: { agent: string; chat: string; text: string };
  add_watchlist: { ticker: string; note?: string | null };
  remove_watchlist: { ticker: string };
  upsert_annotation: { id: string; ticker: string; timeframe?: string | null; drawing: RuntimeDrawing };
  strike_annotation: { id: string };
  approve_order: { order_id: number; confirm: true };
  reject_order: { order_id: number; reason: string };
  halt: { cancel_open?: boolean; confirm: true };
  resume: { confirm: true };
  reconcile_broker: Record<string, never>;
  refresh_data: { kinds?: string[]; force?: boolean };
  mark_inbox_read: { item_id: number };
  /** A note signed by Luca in the ticker's dossier; agents read it as a senior colleague's view. */
  add_dossier_note: { ticker: string; text: string };
  /**
   * Luca decides in the PM's place: same path as the PM, the Risk Gate stays sovereign.
   * Field names beyond `confirm` are the frontend's proposal (.scratch/ticker-agents/wiki-notes-frontend.md).
   */
  decide_proposal: {
    proposal_id: number;
    action: "accept" | "defer" | "reject" | "ask";
    reason: string;
    confirm: true;
    /** accept only: resize the proposal (fraction of equity). */
    sizing_fraction?: number;
    /** defer only: when to look again (YYYY-MM-DD). */
    next_check_date?: string;
  };
  /** Luca forwards a news item with his note: a colleague's opinion in the recipient's chat (.scratch/notizie/handoff-backend.md). */
  forward_news: { news_id: number; to: { agent: string } | { ticker: string }; note: string };
  add_news_source: { provider: "rss"; name: string; url: string };
  set_news_source_enabled: { source_id: number; enabled: boolean };
  remove_news_source: { source_id: number };
  refresh_news: { source_id: number | null };
  // Bridge agent (.scratch/assistente/handoff-backend.md, binding contract).
  /** `conversation_id: null` opens a new conversation; data: {conversation_id, message_id}. */
  bridge_say: {
    conversation_id: number | null;
    text: string;
    context: { page: string; ticker: string | null; ref: { type: string; id: string } | null } | null;
  };
  bridge_rename_conversation: { conversation_id: number; title: string };
  bridge_archive_conversation: { conversation_id: number; archived: boolean };
  bridge_stop: { conversation_id: number };
  /** `confirm` must be true for "confirm": the Runtime reruns the original command from its own handler. */
  bridge_action_decide: { action_id: number; decision: "confirm" | "dismiss"; confirm: boolean };
  mark_briefing_seen: { ts: string };
};
