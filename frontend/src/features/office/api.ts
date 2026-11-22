import { AGENT_IDS } from "@/lib/authors";
import { parseTs } from "@/lib/format";
import { RuntimeError, type RuntimeClient } from "@/lib/runtime/client";
import type { Cycle, Message, WatchlistItem } from "@/lib/runtime/types";
import type { AgentStatus, ChatTopic, OfficeAgent, Sourced, ToolCall, ToolStatus, UsageRow, UsageTotals } from "./types";

/** The chat topic the cockpit writes into when Luca talks to an agent outside a ticker. */
export const COCKPIT_TOPIC = "cockpit";

/** The Runtime answers 404 "Read endpoint 'x' not found" for reads it does not have yet. */
export function isNotExposed(err: unknown): boolean {
  return err instanceof RuntimeError && err.status === 404 && /read endpoint/i.test(err.message);
}

type Row = Record<string, unknown>;

const str = (v: unknown): string | null => (typeof v === "string" && v.length ? v : typeof v === "number" ? String(v) : null);
const num = (v: unknown): number | null => {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
};
const rows = (v: unknown, key: string): Row[] => {
  if (Array.isArray(v)) return v as Row[];
  if (v && typeof v === "object" && Array.isArray((v as Row)[key])) return (v as Row)[key] as Row[];
  return [];
};
const json = (v: unknown): unknown => {
  if (typeof v !== "string") return v;
  try {
    return JSON.parse(v);
  } catch {
    return v;
  }
};

const isTicker = (topic: string) => /^[A-Z][A-Z0-9.]{0,6}$/.test(topic);

export function topicTitle(topic: string): string {
  if (topic === COCKPIT_TOPIC) return "Con Luca";
  if (isTicker(topic)) return topic;
  return topic.replace(/[-_]/g, " ").replace(/^./, (c) => c.toUpperCase());
}

function usageOf(v: unknown): UsageTotals | null {
  if (!v || typeof v !== "object") return null;
  const r = v as Row;
  const cost = num(r.cost ?? r.cost_usd);
  if (cost === null && num(r.tokens_in) === null) return null;
  return { tokens_in: num(r.tokens_in) ?? 0, tokens_out: num(r.tokens_out) ?? 0, cost: cost ?? 0, calls: num(r.calls) ?? 0 };
}

function normalizeAgent(r: Row): OfficeAgent {
  const status = str(r.status);
  // Runtime shape: `current_task: {type, ticker, cycle_id | task_id, description}`.
  const cur = (r.current_task ?? r.current ?? null) as Row | null;
  // Runtime shape: flat `today_tokens_in`, `today_tokens_out`, `today_cost`.
  const flatToday =
    r.today_cost !== undefined || r.today_tokens_in !== undefined
      ? { cost: r.today_cost, tokens_in: r.today_tokens_in, tokens_out: r.today_tokens_out, calls: r.today_calls }
      : null;
  const name = str(r.name ?? r.agent) ?? "sconosciuto";
  // Ticker-agent contract: `kind`, `ticker`, `supervisor`. A Runtime that predates it sends none of them;
  // then the identity `ticker:<SYM>` (same contract) is the only honest signal.
  const prefixed = /^ticker:(.+)$/i.exec(name);
  const kind = r.kind === "ticker" || r.kind === "core" ? r.kind : prefixed ? "ticker" : "core";
  return {
    name,
    kind,
    ticker: kind === "ticker" ? (str(r.ticker) ?? prefixed?.[1]?.toUpperCase() ?? null) : null,
    supervisor: str(r.supervisor),
    role: str(r.role),
    model: str(r.model),
    status: status === "working" || status === "waiting" || status === "idle" ? (status as AgentStatus) : null,
    current: cur
      ? {
          kind: str(cur.type ?? cur.kind) ?? "task",
          id: num(cur.cycle_id ?? cur.task_id ?? cur.id),
          ticker: str(cur.ticker),
          label: str(cur.description ?? cur.label ?? cur.reason),
        }
      : null,
    last_activity_ts: str(r.last_activity_ts ?? r.last_activity),
    today: usageOf(r.today ?? r.usage_today ?? flatToday),
  };
}

function normalizeTopic(agent: string, r: Row): ChatTopic {
  const topic = str(r.topic) ?? COCKPIT_TOPIC;
  const last = (r.last_message ?? null) as Row | null;
  return {
    chat_id: num(r.chat_id ?? r.id),
    agent,
    topic,
    title: str(r.title) ?? topicTitle(topic),
    ticker: str(r.ticker) ?? (isTicker(topic) ? topic : null),
    cycle_id: num(r.cycle_id),
    last_message: last ? { author: str(last.author) ?? "", text: str(last.text) ?? "", ts: str(last.ts) ?? "" } : null,
    message_count: num(r.message_count) ?? 0,
  };
}

function normalizeTool(r: Row): ToolCall {
  const error = str(r.error);
  const status = str(r.status);
  const compacted = r.compacted;
  const c = compacted && typeof compacted === "object" ? (compacted as Row) : null;
  const params = json(r.params ?? r.params_json);
  return {
    id: num(r.id) ?? 0,
    ts: str(r.ts) ?? "",
    agent: str(r.agent) ?? "",
    chat_id: num(r.chat_id),
    topic: str(r.topic),
    cycle_id: num(r.cycle_id),
    tool: str(r.tool) ?? "tool",
    params: params && typeof params === "object" && !Array.isArray(params) ? (params as Record<string, unknown>) : null,
    result: json(r.result ?? r.result_json ?? null),
    status: status === "running" || status === "ok" || status === "error" ? (status as ToolStatus) : error ? "error" : "ok",
    error,
    duration_ms: num(r.duration_ms),
    compacted: {
      params: c ? !!c.params : compacted === true || !!r.params_compacted,
      result: c ? !!c.result : compacted === true || !!r.result_compacted,
      at: c ? str(c.at) : str(r.compacted_at),
    },
  };
}

/** Wraps a read that may not exist yet: 404 becomes `unavailable` or a derived fallback; anything else throws. */
async function exposed<T>(read: () => Promise<T>, fallback: () => Promise<Sourced<T>>): Promise<Sourced<T>> {
  try {
    return { source: "runtime", data: await read() };
  } catch (err) {
    if (isNotExposed(err)) return fallback();
    throw err;
  }
}

/** Recent cycles with their messages: the real trace the derived views are rebuilt from. */
export async function recentCycleMessages(client: RuntimeClient, limit = 12): Promise<Cycle[]> {
  const cycles = await client.cycles({ limit });
  const details = await Promise.all(cycles.map((c) => client.cycle(c.id).catch(() => null)));
  return details.filter((c): c is Cycle => !!c);
}

export function fetchAgents(client: RuntimeClient): Promise<Sourced<OfficeAgent[]>> {
  return exposed(
    async () => rows(await client.read<unknown>("agents"), "agents").map(normalizeAgent),
    async () => {
      const cycles = await recentCycleMessages(client);
      const agents = AGENT_IDS.map<OfficeAgent>((name) => {
        let last: string | null = null;
        let current: OfficeAgent["current"] = null;
        for (const c of cycles) {
          const mine = c.messages.filter((m) => m.author === name);
          for (const m of mine) if (!last || (parseTs(m.ts) ?? 0) > (parseTs(last) ?? 0)) last = m.ts;
          if (!current && c.status === "open" && mine.length) current = { kind: "cycle", id: c.id, ticker: c.ticker, label: null };
        }
        return { name, kind: "core", ticker: null, supervisor: null, role: null, model: null, status: null, current, last_activity_ts: last, today: null };
      });
      return { source: "derived", data: agents, note: "Stato, modello e costi non sono ancora esposti dal Runtime: ultima attività e ciclo corrente vengono dai cicli recenti." };
    },
  );
}

export function fetchTopics(client: RuntimeClient, agent: string): Promise<Sourced<ChatTopic[]>> {
  return exposed(
    async () => rows(await client.read<unknown>("chat_topics", { agent }), "topics").map((r) => normalizeTopic(agent, r)),
    async () => {
      // Without chat_topics, probe the topics that can exist: Luca's thread plus every ticker in recent cycles or the watchlist.
      const [cycles, watch] = await Promise.all([client.cycles({ limit: 30 }).catch(() => [] as Cycle[]), client.watchlist().catch(() => [] as WatchlistItem[])]);
      const candidates = Array.from(new Set([COCKPIT_TOPIC, ...cycles.map((c) => c.ticker), ...watch.map((w) => w.ticker)]));
      const probed = await Promise.all(
        candidates.map(async (topic) => ({ topic, messages: await client.read<Message[]>("chat", { agent, topic, limit: 500 }).catch(() => [] as Message[]) })),
      );
      const topics = probed
        .filter((p) => p.topic === COCKPIT_TOPIC || p.messages.length > 0)
        .map<ChatTopic>(({ topic, messages }) => {
          const last = messages.at(-1);
          return {
            chat_id: last?.chat_id ?? null,
            agent,
            topic,
            title: topicTitle(topic),
            ticker: isTicker(topic) ? topic : null,
            cycle_id: last?.cycle_id ?? null,
            last_message: last ? { author: last.author, text: last.text, ts: last.ts } : null,
            message_count: messages.length,
          };
        });
      return { source: "derived", data: topics, note: "Elenco ricostruito dai cicli e dalla watchlist: il Runtime non espone ancora le chat per agente." };
    },
  );
}

export async function fetchChat(client: RuntimeClient, agent: string, topic: string): Promise<Message[]> {
  return client.read<Message[]>("chat", { agent, topic, limit: 500 });
}

export function fetchToolCalls(client: RuntimeClient, agent: string, limit = 100): Promise<Sourced<ToolCall[]>> {
  return exposed(
    async () => rows(await client.read<unknown>("tool_calls", { agent, limit }), "tool_calls").map(normalizeTool),
    async () => ({ source: "unavailable", note: "Il Runtime non espone ancora le chiamate ai tool." }),
  );
}

export function fetchUsage(client: RuntimeClient, params: { agent?: string; from?: string; to?: string }): Promise<Sourced<UsageRow[]>> {
  return exposed(
    async () => {
      const raw = await client.read<unknown>("usage", params);
      const list = Array.isArray(raw) || (raw && typeof raw === "object" && "rows" in raw) ? rows(raw, "rows") : raw ? [raw as Row] : [];
      return list.map((r) => ({ agent: str(r.agent) ?? params.agent ?? "", ...(usageOf(r) ?? { tokens_in: 0, tokens_out: 0, cost: 0, calls: 0 }) }));
    },
    async () => ({ source: "unavailable", note: "Costi e token non sono ancora esposti dal Runtime." }),
  );
}
