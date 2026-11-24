// Types of the Configurazioni contract (.scratch/configurazioni/handoff-backend.md). Field names are the contract's,
// unchanged: the adapters in api.ts pass the Runtime's JSON through and only fill gaps with null.

export type { Sourced } from "@/features/office/types";

export type SettingType = "int" | "float" | "string" | "enum" | "time" | "bool";
export type ApplyMode = "live" | "restart";
export type SettingValue = string | number | boolean | null;

/** One editable key, `GET /v1/read/settings` → `sections[].items[]`. */
export type SettingItem = {
  key: string;
  label: string;
  description: string;
  type: SettingType;
  value: SettingValue;
  default: SettingValue;
  min: number | null;
  max: number | null;
  options: string[] | null;
  unit: string | null;
  apply: ApplyMode;
  capital: boolean;
  overridden: boolean;
};

export type SettingsSection = { id: string; title: string; items: SettingItem[] };

/** `GET /v1/read/settings` */
export type SettingsRead = {
  version: number;
  updated_ts: string | null;
  updated_by: string | null;
  pending_restart: string[];
  sections: SettingsSection[];
};

/** `GET /v1/read/settings_history?limit=` */
export type SettingsVersion = {
  version: number;
  ts: string;
  actor: string;
  reason: string;
  changes: { key: string; old: SettingValue; new: SettingValue }[];
};

/** `GET /v1/read/agent_configs` */
export type AgentConfig = {
  agent: string;
  role: string | null;
  model: string | null;
  endpoint: string | null;
  effort: string | null;
  daily_budget_usd: number | null;
  today_cost: number | null;
  prompt_version: number | null;
  prompt_updated_ts: string | null;
};

/** `GET /v1/read/prompt?agent=` */
export type PromptRead = {
  agent: string;
  version: number;
  text: string;
  updated_ts: string | null;
  updated_by: string | null;
  reason: string | null;
  is_default: boolean;
};

/** `GET /v1/read/prompt_history?agent=&limit=` */
export type PromptVersion = { version: number; ts: string; actor: string; reason: string; chars: number | null };

export type SecretSource = "store" | "env" | "none";
export type ConnectionTest = { ok: boolean; detail: string | null; ts: string | null };

/** `GET /v1/read/secrets`: never a value, only whether it is set and its last 4 characters. */
export type SecretStatus = {
  name: string;
  label: string;
  set: boolean;
  last4: string | null;
  updated_ts: string | null;
  updated_by: string | null;
  source: SecretSource;
  test: ConnectionTest | null;
};

export type JobHealth = {
  name: string;
  last_run_ts: string | null;
  last_status: "ok" | "error" | null;
  last_error: string | null;
  next_run_ts: string | null;
};

/** `GET /v1/read/runtime_health` */
export type RuntimeHealth = {
  version: string | null;
  commit: string | null;
  started_ts: string | null;
  uptime_s: number | null;
  db: { path_label: string | null; size_bytes: number | null; wal_bytes: number | null; alert_mb: number | null; last_backup_ts: string | null };
  jobs: JobHealth[];
  errors: { ts: string; source: string; message: string }[];
  sse_clients: number | null;
  broker: { ok: boolean; detail: string | null };
  llm: { ok: boolean; detail: string | null };
};

/** `GET /v1/read/backups` */
export type Backup = { name: string; ts: string; size_bytes: number | null };

// ---------- commands ----------

export type SettingsChangePreview = { key: string; old: SettingValue; new: SettingValue; apply: ApplyMode; ok: boolean; reason: string | null };
/** `update_settings` dry run → `data` */
export type SettingsPreview = { changes: SettingsChangePreview[]; warnings: string[] };

export type UpdateSettingsPayload = { changes: Record<string, SettingValue>; reason: string; confirm: boolean; dry_run: boolean };
export type RestoreSettingsPayload = { version: number; reason: string };
export type UpdatePromptPayload = { agent: string; text: string; reason: string; dry_run: boolean };
export type RestorePromptPayload = { agent: string; version: number; reason: string };
export type SetSecretPayload = { name: string; value: string; reason: string; confirm: boolean };
export type ClearSecretPayload = { name: string; reason: string; confirm: true };
export type TestTarget = "omniroute" | "alpaca" | "openbb";

/** `set_secret` → `data` */
export type SecretResult = { name: string; set: boolean; last4: string | null; test: { ok: boolean; detail: string | null } | null };

export type DiffLine = { op: "eq" | "add" | "del"; text: string };
