// Contracts the Ufficio reads. `/v1/read/agents`, `chat_topics`, `tool_calls` and `usage` are proposed by
// the frontend (see .scratch/cockpit/handoff-backend-ufficio.md) and land with the `backend-ufficio` branch;
// until then the adapters in ./api.ts derive what real data allows and mark the rest unavailable.

export type AgentStatus = "working" | "waiting" | "idle";

/** What an agent is doing now: an analysis cycle or a scheduled task, usually on a ticker. */
export type AgentWork = {
  kind: "cycle" | "task" | string;
  id: number | null;
  ticker: string | null;
  label: string | null;
};

export type UsageTotals = {
  tokens_in: number;
  tokens_out: number;
  cost: number;
  calls: number;
};

/** One row of `GET /v1/read/agents`. */
export type OfficeAgent = {
  name: string;
  role: string | null;
  model: string | null;
  /** Null when the Runtime does not expose it (derived mode). */
  status: AgentStatus | null;
  current: AgentWork | null;
  last_activity_ts: string | null;
  /** Null when usage is not exposed. */
  today: UsageTotals | null;
};

export type LastMessage = { author: string; text: string; ts: string };

/** One row of `GET /v1/read/chat_topics?agent=`. `topic` is the key `say` and `/v1/read/chat` take. */
export type ChatTopic = {
  chat_id: number | null;
  agent: string;
  topic: string;
  title: string;
  ticker: string | null;
  cycle_id: number | null;
  last_message: LastMessage | null;
  message_count: number;
};

export type ToolStatus = "running" | "ok" | "error";

/** One row of `GET /v1/read/tool_calls?agent=&cycle=&after=&limit=`. */
export type ToolCall = {
  id: number;
  ts: string;
  agent: string;
  chat_id: number | null;
  topic: string | null;
  cycle_id: number | null;
  tool: string;
  params: Record<string, unknown> | null;
  result: unknown;
  status: ToolStatus;
  error: string | null;
  duration_ms: number | null;
  /** Retention compacted the stored payload: the UI says so instead of showing an empty block. */
  compacted: { params: boolean; result: boolean; at: string | null };
};

/** One row of `GET /v1/read/usage?agent=&from=&to=`. */
export type UsageRow = UsageTotals & { agent: string };

/**
 * Where a read came from. `runtime`: the endpoint answered. `derived`: the endpoint is missing and the value
 * was rebuilt from other real reads (`note` says how). `unavailable`: nothing honest to show.
 */
export type Sourced<T> =
  | { source: "runtime"; data: T }
  | { source: "derived"; data: T; note: string }
  | { source: "unavailable"; note: string };
