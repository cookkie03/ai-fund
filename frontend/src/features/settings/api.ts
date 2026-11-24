import { isNotExposed } from "@/features/office/api";
import { isCommandMissing } from "@/features/portfolio/api";
import { toNum } from "@/lib/format";
import { RuntimeError, type RuntimeClient } from "@/lib/runtime/client";
import type { CommandResult } from "@/lib/runtime/types";
import type {
  AgentConfig,
  Backup,
  ClearSecretPayload,
  DiffLine,
  PromptRead,
  PromptVersion,
  RestorePromptPayload,
  RestoreSettingsPayload,
  RuntimeHealth,
  SecretResult,
  SecretStatus,
  SetSecretPayload,
  SettingItem,
  SettingsPreview,
  SettingsRead,
  SettingsVersion,
  SettingValue,
  Sourced,
  TestTarget,
  UpdatePromptPayload,
  UpdateSettingsPayload,
} from "./types";

// Adapters for the Configurazioni reads and commands. Each read asks the contract endpoint; a 404 "Read endpoint
// not found" means the backend has not landed yet and the adapter answers `unavailable` with the endpoint's name.
// Nothing is rebuilt or guessed here: configuration has no honest substitute.

type Row = Record<string, unknown>;

const str = (v: unknown): string | null => (typeof v === "string" && v.length ? v : typeof v === "number" ? String(v) : null);
const num = (v: unknown): number | null => toNum(v);
const arr = (v: unknown): Row[] => (Array.isArray(v) ? (v as Row[]) : []);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);
const scalar = (v: unknown): SettingValue => (typeof v === "string" || typeof v === "number" || typeof v === "boolean" ? v : null);

async function exposed<T>(endpoint: string, what: string, read: () => Promise<T>): Promise<Sourced<T>> {
  try {
    return { source: "runtime", data: await read() };
  } catch (err) {
    if (isNotExposed(err)) return { source: "unavailable", note: `${what} ${/^(Le|I|Gli) /.test(what) ? "arrivano" : "arriva"} con /v1/read/${endpoint}, che il Runtime non espone ancora.` };
    throw err;
  }
}

/** Endpoint each read waits for, for the "non disponibile" notes. */
export const ENDPOINT = {
  settings: "settings",
  history: "settings_history",
  agents: "agent_configs",
  prompt: "prompt",
  promptHistory: "prompt_history",
  secrets: "secrets",
  health: "runtime_health",
  backups: "backups",
} as const;

function normItem(r: Row): SettingItem {
  const type = str(r.type);
  return {
    key: str(r.key) ?? "?",
    label: str(r.label) ?? str(r.key) ?? "?",
    description: str(r.description) ?? "",
    type: type === "int" || type === "float" || type === "string" || type === "enum" || type === "time" || type === "bool" ? type : "string",
    value: scalar(r.value),
    default: scalar(r.default),
    min: num(r.min),
    max: num(r.max),
    options: Array.isArray(r.options) ? strs(r.options) : null,
    unit: str(r.unit),
    apply: r.apply === "restart" ? "restart" : "live",
    capital: r.capital === true,
    overridden: r.overridden === true,
  };
}

export function fetchSettings(client: RuntimeClient): Promise<Sourced<SettingsRead>> {
  return exposed(ENDPOINT.settings, "Le impostazioni", async () => {
    const d = (await client.read<Row>("settings")) ?? {};
    return {
      version: num(d.version) ?? 0,
      updated_ts: str(d.updated_ts),
      updated_by: str(d.updated_by),
      pending_restart: strs(d.pending_restart),
      sections: arr(d.sections).map((s) => ({ id: str(s.id) ?? "?", title: str(s.title) ?? str(s.id) ?? "?", items: arr(s.items).map(normItem) })),
    };
  });
}

export function fetchSettingsHistory(client: RuntimeClient, limit = 30): Promise<Sourced<SettingsVersion[]>> {
  return exposed(ENDPOINT.history, "Lo storico delle impostazioni", async () =>
    arr(await client.read<unknown>("settings_history", { limit })).map((h) => ({
      version: num(h.version) ?? 0,
      ts: str(h.ts) ?? "",
      actor: str(h.actor) ?? "",
      reason: str(h.reason) ?? "",
      changes: arr(h.changes).map((c) => ({ key: str(c.key) ?? "?", old: scalar(c.old), new: scalar(c.new) })),
    })),
  );
}

export function fetchAgentConfigs(client: RuntimeClient): Promise<Sourced<AgentConfig[]>> {
  return exposed(ENDPOINT.agents, "La configurazione degli agenti", async () =>
    arr(await client.read<unknown>("agent_configs")).map((a) => ({
      agent: str(a.agent) ?? "?",
      role: str(a.role),
      model: str(a.model),
      endpoint: str(a.endpoint),
      effort: str(a.effort),
      daily_budget_usd: num(a.daily_budget_usd),
      today_cost: num(a.today_cost),
      prompt_version: num(a.prompt_version),
      prompt_updated_ts: str(a.prompt_updated_ts),
    })),
  );
}

export function fetchPrompt(client: RuntimeClient, agent: string): Promise<Sourced<PromptRead>> {
  return exposed(ENDPOINT.prompt, "Il prompt", async () => {
    const d = (await client.read<Row>("prompt", { agent })) ?? {};
    return {
      agent: str(d.agent) ?? agent,
      version: num(d.version) ?? 0,
      text: typeof d.text === "string" ? d.text : "",
      updated_ts: str(d.updated_ts),
      updated_by: str(d.updated_by),
      reason: str(d.reason),
      is_default: d.is_default === true,
    };
  });
}

export function fetchPromptHistory(client: RuntimeClient, agent: string, limit = 20): Promise<Sourced<PromptVersion[]>> {
  return exposed(ENDPOINT.promptHistory, "Le versioni del prompt", async () =>
    arr(await client.read<unknown>("prompt_history", { agent, limit })).map((h) => ({
      version: num(h.version) ?? 0,
      ts: str(h.ts) ?? "",
      actor: str(h.actor) ?? "",
      reason: str(h.reason) ?? "",
      chars: num(h.chars),
    })),
  );
}

const testOf = (v: unknown) => {
  if (!v || typeof v !== "object") return null;
  const t = v as Row;
  return { ok: t.ok === true, detail: str(t.detail), ts: str(t.ts) };
};

export function fetchSecrets(client: RuntimeClient): Promise<Sourced<SecretStatus[]>> {
  return exposed(ENDPOINT.secrets, "Lo stato delle chiavi", async () =>
    // Only the contract's fields are copied: if the Runtime ever sent more, nothing else reaches the cache.
    arr(await client.read<unknown>("secrets")).map((s) => ({
      name: str(s.name) ?? "?",
      label: str(s.label) ?? str(s.name) ?? "?",
      set: s.set === true,
      last4: str(s.last4)?.slice(-4) ?? null,
      updated_ts: str(s.updated_ts),
      updated_by: str(s.updated_by),
      source: s.source === "store" || s.source === "env" ? s.source : "none",
      test: testOf(s.test),
    })),
  );
}

const okOf = (v: unknown) => {
  const r = (v && typeof v === "object" ? v : {}) as Row;
  return { ok: r.ok === true, detail: str(r.detail) };
};

export function fetchRuntimeHealth(client: RuntimeClient): Promise<Sourced<RuntimeHealth>> {
  return exposed(ENDPOINT.health, "La salute del Runtime", async () => {
    const d = (await client.read<Row>("runtime_health")) ?? {};
    const db = (d.db && typeof d.db === "object" ? d.db : {}) as Row;
    return {
      version: str(d.version),
      commit: str(d.commit),
      started_ts: str(d.started_ts),
      uptime_s: num(d.uptime_s),
      db: { path_label: str(db.path_label), size_bytes: num(db.size_bytes), wal_bytes: num(db.wal_bytes), alert_mb: num(db.alert_mb), last_backup_ts: str(db.last_backup_ts) },
      jobs: arr(d.jobs).map((j) => ({
        name: str(j.name) ?? "?",
        last_run_ts: str(j.last_run_ts),
        last_status: j.last_status === "ok" || j.last_status === "error" ? j.last_status : null,
        last_error: str(j.last_error),
        next_run_ts: str(j.next_run_ts),
      })),
      errors: arr(d.errors).map((e) => ({ ts: str(e.ts) ?? "", source: str(e.source) ?? "", message: str(e.message) ?? "" })),
      sse_clients: num(d.sse_clients),
      broker: okOf(d.broker),
      llm: okOf(d.llm),
    };
  });
}

export function fetchBackups(client: RuntimeClient): Promise<Sourced<Backup[]>> {
  return exposed(ENDPOINT.backups, "L'elenco dei backup", async () =>
    arr(await client.read<unknown>("backups")).map((b) => ({ name: str(b.name) ?? "?", ts: str(b.ts) ?? "", size_bytes: num(b.size_bytes) })),
  );
}

// ---------- commands ----------

export { isCommandMissing };

export type Outcome<T> = { ok: true; data: T } | { ok: false; reasons: string[]; data: T | null };

async function run<T>(client: RuntimeClient, name: string, payload: object, norm: (d: Row) => T): Promise<Outcome<T>> {
  // The Configurazioni commands are not in the typed CommandName union until the backend lands.
  const send = client.command.bind(client) as unknown as (n: string, p: object) => Promise<CommandResult>;
  const res = await send(name, payload);
  const data = res.data && typeof res.data === "object" ? norm(res.data as Row) : null;
  if (!res.ok) return { ok: false, reasons: res.reasons ?? [], data };
  return { ok: true, data: data ?? norm({}) };
}

function normPreview(d: Row): SettingsPreview {
  return {
    changes: arr(d.changes).map((c) => ({
      key: str(c.key) ?? "?",
      old: scalar(c.old),
      new: scalar(c.new),
      apply: c.apply === "restart" ? "restart" : "live",
      ok: c.ok !== false,
      reason: str(c.reason),
    })),
    warnings: strs(d.warnings),
  };
}

/** The server's diff when it is a list of `{op, text}` lines; null otherwise (the page computes it locally). */
function normDiff(v: unknown): DiffLine[] | null {
  if (!Array.isArray(v)) return null;
  const out: DiffLine[] = [];
  for (const l of v as Row[]) {
    const op = l?.op === "add" || l?.op === "del" || l?.op === "eq" ? l.op : null;
    if (!op || typeof l.text !== "string") return null;
    out.push({ op, text: l.text });
  }
  return out;
}

export const updateSettings = (c: RuntimeClient, p: UpdateSettingsPayload) => run(c, "update_settings", p, normPreview);
export const restoreSettings = (c: RuntimeClient, p: RestoreSettingsPayload) => run(c, "restore_settings", p, (d) => d);
export const updatePrompt = (c: RuntimeClient, p: UpdatePromptPayload) => run(c, "update_prompt", p, (d) => ({ diff: normDiff(d.diff), version: num(d.version) }));
export const restorePrompt = (c: RuntimeClient, p: RestorePromptPayload) => run(c, "restore_prompt", p, (d) => d);
export const backupDb = (c: RuntimeClient) => run(c, "backup_db", {}, (d) => ({ name: str(d.name) }));
export const testConnection = (c: RuntimeClient, target: TestTarget) => run(c, "test_connection", { target }, (d) => ({ ok: d.ok === true, detail: str(d.detail) }));
export const clearSecret = (c: RuntimeClient, p: ClearSecretPayload) => run(c, "clear_secret", p, (d) => ({ name: str(d.name) }));

/**
 * Sends a key. Deliberately not a react-query mutation: a mutation keeps its variables (the key) in the
 * MutationCache. The result is rebuilt field by field from the contract so no echoed value can be kept.
 */
export const setSecret = (c: RuntimeClient, p: SetSecretPayload) =>
  run<SecretResult>(c, "set_secret", p, (d) => ({
    name: str(d.name) ?? p.name,
    set: d.set === true,
    last4: str(d.last4)?.slice(-4) ?? null,
    test: d.test && typeof d.test === "object" ? okOf(d.test) : null,
  }));

/** Why a command failed, in words, naming the command when the Runtime does not have it yet. */
export function commandFailure(err: unknown, name: string): string {
  if (isCommandMissing(err)) return `Il Runtime non espone ancora il comando ${name}: nulla è stato applicato.`;
  if (err instanceof RuntimeError && err.unreachable) return "Runtime irraggiungibile: il comando non è stato inviato.";
  return err instanceof Error ? err.message : String(err);
}

/** Which connection test a key belongs to. */
export function testTargetFor(name: string): TestTarget | null {
  const n = name.toUpperCase();
  if (n.startsWith("OMNIROUTE")) return "omniroute";
  if (n.startsWith("ALPACA")) return "alpaca";
  if (n.startsWith("OPENBB")) return "openbb";
  return null;
}

export const isBrokerKey = (name: string) => name.toUpperCase().startsWith("ALPACA");

/** Line diff (LCS) between two texts; used when the Runtime's preview carries no diff. */
export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  // Trim the common head and tail so long prompts with a local edit stay cheap.
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head++;
  let tail = 0;
  while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail++;
  const am = a.slice(head, a.length - tail);
  const bm = b.slice(head, b.length - tail);
  const n = am.length;
  const m = bm.length;
  const out: DiffLine[] = a.slice(0, head).map((text) => ({ op: "eq", text }));
  if (n * m > 4_000_000) {
    // Pathological size: show it as a replacement rather than freezing the tab.
    out.push(...am.map((text) => ({ op: "del" as const, text })), ...bm.map((text) => ({ op: "add" as const, text })));
  } else {
    const dp = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = am[i] === bm[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    let i = 0;
    let j = 0;
    while (i < n && j < m) {
      if (am[i] === bm[j]) {
        out.push({ op: "eq", text: am[i] });
        i++;
        j++;
      } else if (dp[i + 1][j] >= dp[i][j + 1]) out.push({ op: "del", text: am[i++] });
      else out.push({ op: "add", text: bm[j++] });
    }
    while (i < n) out.push({ op: "del", text: am[i++] });
    while (j < m) out.push({ op: "add", text: bm[j++] });
  }
  out.push(...a.slice(a.length - tail).map((text) => ({ op: "eq" as const, text })));
  return out;
}
