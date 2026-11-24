import { isNotExposed } from "@/features/office/api";
import { RuntimeError, type RuntimeClient } from "@/lib/runtime/client";
import type {
  ActionPreview,
  ActionStatus,
  Briefing,
  BriefingItem,
  BridgeAction,
  BridgeContext,
  BridgeMessage,
  BridgeRead,
  Conversation,
  ConversationSummary,
  MessageKind,
  MessageRef,
  Severity,
} from "./types";

// Adapters for the Bridge reads. They read exactly the contract's field names
// (.scratch/assistente/handoff-backend.md) and only coerce types: no aliases, no guessed names.
// A 404 "Read endpoint 'x' not found" means the Runtime predates the Bridge: `unavailable` + endpoint.

type Row = Record<string, unknown>;

const obj = (v: unknown): Row | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Row) : null);
const arr = (v: unknown): Row[] => (Array.isArray(v) ? (v.filter((x) => obj(x)) as Row[]) : []);
const str = (v: unknown): string | null => (typeof v === "string" && v.length ? v : typeof v === "number" ? String(v) : null);
const num = (v: unknown): number | null => {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
};
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.map(str).filter((s): s is string => !!s) : []);

export const ENDPOINT = {
  conversations: "GET /v1/read/bridge_conversations",
  conversation: "GET /v1/read/bridge_conversation",
  actions: "GET /v1/read/bridge_actions",
  briefing: "GET /v1/read/briefing",
} as const;

const ACTION_STATUS: ActionStatus[] = ["pending", "confirmed", "dismissed", "executed", "failed"];
const KINDS: MessageKind[] = ["text", "agent_relay", "action", "error"];
const SEVERITY: Severity[] = ["info", "attention", "critical"];

function refOf(v: unknown): { type: string; id: string } | null {
  const r = obj(v);
  if (!r) return null;
  const type = str(r.type);
  const id = str(r.id);
  return type && id ? { type, id } : null;
}

function context(v: unknown): BridgeContext | null {
  const r = obj(v);
  if (!r) return null;
  return { page: str(r.page) ?? "", ticker: str(r.ticker), ref: refOf(r.ref) };
}

function preview(v: unknown): ActionPreview | null {
  const r = obj(v);
  if (!r) return null;
  return { ok: r.ok === true, reasons: strs(r.reasons), detail: obj(r.detail) };
}

export function normalizeAction(r: Row): BridgeAction {
  const status = str(r.status) as ActionStatus | null;
  return {
    id: num(r.id) ?? 0,
    command: str(r.command) ?? "",
    payload: obj(r.payload) ?? {},
    summary: str(r.summary) ?? "",
    capital: r.capital !== false,
    status: status && ACTION_STATUS.includes(status) ? status : "pending",
    preview: preview(r.preview),
    result_reasons: strs(r.result_reasons),
    decided_ts: str(r.decided_ts),
    decided_by: str(r.decided_by),
    conversation_id: num(r.conversation_id),
  };
}

export function normalizeMessage(r: Row): BridgeMessage {
  const kind = str(r.kind) as MessageKind | null;
  const action = obj(r.action);
  return {
    id: num(r.id) ?? 0,
    conversation_id: num(r.conversation_id) ?? 0,
    author: str(r.author) ?? "",
    kind: kind && KINDS.includes(kind) ? kind : "text",
    text: str(r.text) ?? "",
    ts: str(r.ts) ?? "",
    context: context(r.context),
    refs: arr(r.refs)
      .map<MessageRef | null>((x) => {
        const type = str(x.type);
        const id = str(x.id);
        return type && id ? { type, id, label: str(x.label) } : null;
      })
      .filter((x): x is MessageRef => !!x),
    action: action ? normalizeAction(action) : null,
  };
}

export function normalizeSummary(r: Row): ConversationSummary {
  const last = obj(r.last_message);
  return {
    id: num(r.id) ?? 0,
    title: str(r.title) ?? "",
    created_ts: str(r.created_ts) ?? "",
    updated_ts: str(r.updated_ts) ?? "",
    message_count: num(r.message_count) ?? 0,
    status: r.status === "thinking" ? "thinking" : "idle",
    archived: r.archived === true,
    last_message: last ? { author: str(last.author) ?? "", text: str(last.text) ?? "", ts: str(last.ts) ?? "" } : null,
    pending_actions: num(r.pending_actions) ?? 0,
  };
}

function conversation(v: unknown): Conversation | null {
  const r = obj(v);
  if (!r || num(r.id) === null) return null;
  return {
    id: num(r.id)!,
    title: str(r.title) ?? "",
    created_ts: str(r.created_ts) ?? "",
    updated_ts: str(r.updated_ts) ?? "",
    status: r.status === "thinking" ? "thinking" : "idle",
    archived: r.archived === true,
    messages: arr(r.messages).map(normalizeMessage),
  };
}

function briefingItem(r: Row): BriefingItem {
  const sev = str(r.severity) as Severity | null;
  return {
    id: str(r.id) ?? "",
    type: str(r.type) ?? "",
    ts: str(r.ts) ?? "",
    title: str(r.title) ?? "",
    detail: str(r.detail),
    ticker: str(r.ticker),
    ref: refOf(r.ref),
    severity: sev && SEVERITY.includes(sev) ? sev : "info",
  };
}

function briefing(v: unknown): Briefing | null {
  const r = obj(v);
  if (!r) return null;
  const pf = obj(r.portfolio);
  const c = obj(r.counts) ?? {};
  return {
    since: str(r.since) ?? "",
    generated_ts: str(r.generated_ts) ?? "",
    summary_text: str(r.summary_text),
    summary_ts: str(r.summary_ts),
    portfolio: pf && num(pf.value) !== null ? { value: num(pf.value)!, change: num(pf.change), change_fraction: num(pf.change_fraction) } : null,
    counts: {
      trades: num(c.trades) ?? 0,
      orders_pending: num(c.orders_pending) ?? 0,
      proposals_pending: num(c.proposals_pending) ?? 0,
      proposals_decided: num(c.proposals_decided) ?? 0,
      alerts: num(c.alerts) ?? 0,
      agent_errors: num(c.agent_errors) ?? 0,
    },
    items: arr(r.items).map(briefingItem),
  };
}

async function guarded<T>(endpoint: string, read: () => Promise<T | null>): Promise<BridgeRead<T>> {
  try {
    const data = await read();
    return data === null ? { state: "missing" } : { state: "ok", data };
  } catch (err) {
    if (isNotExposed(err)) return { state: "unavailable", endpoint };
    if (err instanceof RuntimeError && err.status === 404) return { state: "missing" };
    throw err;
  }
}

export function fetchConversations(client: RuntimeClient, params: { q?: string; archived?: boolean; limit?: number }): Promise<BridgeRead<ConversationSummary[]>> {
  return guarded(ENDPOINT.conversations, async () =>
    arr(await client.read<unknown>("bridge_conversations", { limit: params.limit ?? 100, q: params.q || undefined, archived: params.archived ?? false })).map(normalizeSummary),
  );
}

export function fetchConversation(client: RuntimeClient, id: number, limit = 100): Promise<BridgeRead<Conversation>> {
  return guarded(ENDPOINT.conversation, async () => conversation(await client.read<unknown>("bridge_conversation", { id, limit })));
}

export function fetchActions(client: RuntimeClient, status?: string): Promise<BridgeRead<BridgeAction[]>> {
  return guarded(ENDPOINT.actions, async () => arr(await client.read<unknown>("bridge_actions", { status })).map(normalizeAction));
}

export function fetchBriefing(client: RuntimeClient, since?: string): Promise<BridgeRead<Briefing>> {
  return guarded(ENDPOINT.briefing, async () => briefing(await client.read<unknown>("briefing", { since })));
}
