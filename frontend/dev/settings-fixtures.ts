// Development only. Answers the Configurazioni reads and commands the Runtime does not expose yet, with synthetic
// data shaped exactly like the contract in .scratch/configurazioni/handoff-backend.md, so every state of the page
// can be designed before the backend lands. Enabled only by `COCKPIT_SETTINGS_FIXTURES` on `vite` (serve): it never
// reaches a build. `=1` is the busy office (history, a restart pending, a failed key test, a job in error, DB over
// its threshold); `=empty` is a fresh install (defaults only, no history, keys missing, no backups).
// No real key exists here: values sent to set_secret are reduced to their last 4 characters and dropped.
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;
const iso = (ms: number) => new Date(ms).toISOString();
const ago = (ms: number) => iso(Date.now() - ms);

type Val = string | number | boolean;
type Item = { key: string; label: string; description: string; type: string; value: Val; default: Val; min: number | null; max: number | null; options: string[] | null; unit: string | null; apply: "live" | "restart"; capital: boolean };
type Section = { id: string; title: string; items: Item[] };

const AGENTS: { id: string; role: string; model: string; effort: string; budget: number; cost: number }[] = [
  { id: "portfolio_manager", role: "Decide le proposte e il dimensionamento", model: "claude-opus-5-5", effort: "high", budget: 10, cost: 4.82 },
  { id: "technical_analyst", role: "Grafici, livelli e segnali", model: "claude-sonnet-5-5", effort: "medium", budget: 6, cost: 2.31 },
  { id: "market_analyst", role: "Contesto macro e settori", model: "claude-sonnet-5-5", effort: "medium", budget: 4, cost: 1.12 },
  { id: "sentiment_analyst", role: "Notizie e sentiment", model: "claude-haiku-5-5", effort: "low", budget: 3, cost: 0.64 },
  { id: "fundamental_analyst", role: "Bilanci e valutazioni", model: "claude-sonnet-5-5", effort: "medium", budget: 4, cost: 0.97 },
  { id: "risk_analyst", role: "Esposizione e scenari", model: "claude-sonnet-5-5", effort: "high", budget: 4, cost: 1.48 },
  { id: "ticker_agent", role: "Configurazione unica degli agenti del ticker", model: "claude-haiku-5-5", effort: "low", budget: 8, cost: 3.05 },
];

const ENDPOINT = "http://127.0.0.1:20128/v1";
const MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2"];

function item(p: Partial<Item> & Pick<Item, "key" | "label" | "type" | "value">): Item {
  return { description: "", default: p.value, min: null, max: null, options: null, unit: null, apply: "live", capital: false, ...p };
}

function defaults(): Section[] {
  return [
    {
      id: "agents",
      title: "Agenti",
      items: AGENTS.flatMap((a) => [
        item({ key: `agents.${a.id}.model`, label: "Modello", description: "Modello chiamato attraverso OmniRoute.", type: "enum", value: a.model, options: MODELS }),
        item({ key: `agents.${a.id}.endpoint`, label: "Endpoint", description: "URL OpenAI-compatibile del provider.", type: "string", value: ENDPOINT, apply: "restart" }),
        item({ key: `agents.${a.id}.effort`, label: "Effort", description: "Quanto ragiona il modello prima di rispondere.", type: "enum", value: a.effort, options: ["low", "medium", "high"] }),
        item({ key: `agents.${a.id}.daily_budget_usd`, label: "Budget giornaliero", description: "Oltre questa spesa l'agente si ferma fino a domani.", type: "float", value: a.budget, min: 0, max: 100, unit: "$" }),
      ]),
    },
    {
      id: "budgets",
      title: "Budget dell'ufficio",
      items: [
        item({ key: "budgets.office_daily_usd", label: "Budget giornaliero dell'ufficio", description: "Tetto di spesa di tutti gli agenti insieme.", type: "float", value: 40, min: 1, max: 500, unit: "$" }),
        item({ key: "budgets.alert_fraction", label: "Avviso di spesa", description: "Quota del budget oltre cui la barra in alto avvisa.", type: "float", value: 80, min: 10, max: 100, unit: "%" }),
      ],
    },
    {
      id: "schedule",
      title: "Orari e cadenza",
      items: [
        item({ key: "schedule.market_open", label: "Apertura del mercato", description: "Ora di New York in cui partono i cicli di sessione.", type: "time", value: "09:30", apply: "restart" }),
        item({ key: "schedule.market_close", label: "Chiusura del mercato", description: "Ora di New York in cui si fermano i cicli di sessione.", type: "time", value: "16:00", apply: "restart" }),
        item({ key: "schedule.premarket_scan", label: "Scansione pre-mercato", description: "Ora di New York del giro di notizie prima dell'apertura.", type: "time", value: "08:45", apply: "restart" }),
        item({ key: "schedule.cycle_minutes", label: "Cadenza dei cicli", description: "Ogni quanti minuti un agente del ticker riguarda il suo titolo.", type: "int", value: 30, min: 5, max: 240, unit: "min" }),
        item({ key: "max_parallel", label: "Cicli in parallelo", description: "Quanti cicli possono girare insieme.", type: "int", value: 3, min: 1, max: 8 }),
        item({ key: "scheduled_task_min_days", label: "Task programmati: minimo", description: "Anticipo minimo con cui un agente può programmare un task.", type: "int", value: 1, min: 0, max: 30, unit: "giorni" }),
        item({ key: "scheduled_task_max_days", label: "Task programmati: massimo", description: "Orizzonte massimo di un task programmato.", type: "int", value: 21, min: 1, max: 90, unit: "giorni" }),
      ],
    },
    {
      id: "market",
      title: "Mercato",
      items: [
        item({ key: "market.bar_timeframe", label: "Timeframe delle barre", description: "Barre su cui gli agenti calcolano indicatori e segnali.", type: "enum", value: "1h", options: ["15m", "1h", "4h", "1d"], apply: "restart" }),
        item({ key: "market.extended_hours", label: "Ore estese", description: "Analizza anche pre e post mercato.", type: "bool", value: false }),
        item({ key: "approval_mode", label: "Approvazione degli ordini", description: "Chi approva gli ordini prima dell'invio al broker.", type: "enum", value: "auto", options: ["auto", "manual_above_threshold", "manual"], capital: true }),
      ],
    },
    {
      id: "retention",
      title: "Retention",
      items: [
        item({ key: "retention.messages_days", label: "Messaggi degli agenti", description: "Dopo quanti giorni i messaggi vengono compattati.", type: "int", value: 180, min: 7, max: 3650, unit: "giorni" }),
        item({ key: "retention.tool_payload_days", label: "Payload dei tool", description: "Dopo quanti giorni input e output dei tool vengono ridotti a un riassunto.", type: "int", value: 30, min: 1, max: 365, unit: "giorni" }),
        item({ key: "retention.events_days", label: "Eventi", description: "Dopo quanti giorni gli eventi SSE vengono eliminati.", type: "int", value: 90, min: 7, max: 3650, unit: "giorni" }),
        item({ key: "db_size_alert_mb", label: "Soglia di avviso del database", description: "Oltre questa dimensione la Salute del Runtime avvisa.", type: "int", value: 1200, min: 100, max: 50_000, unit: "MB" }),
      ],
    },
  ];
}

const LONG_PM = [
  "# Portfolio Manager",
  "",
  "Sei il Portfolio Manager dell'ufficio. Ricevi le proposte degli agenti del ticker e decidi se accettarle, rimandarle o rifiutarle.",
  "",
  "## Principi",
  ...Array.from({ length: 40 }, (_, i) => `${i + 1}. ${["Il Risk Gate è sovrano: non proporre ordini che lo violano.", "Dimensiona sul rischio fino allo stop, non sul valore.", "Preferisci poche posizioni ad alta convinzione.", "Leggi le note di Luca prima di decidere.", "Spiega ogni decisione in tre frasi al massimo."][i % 5]}`),
  "",
  "## Formato della risposta",
  "Rispondi in JSON con i campi decision, size_fraction, reason.",
  "",
  "## Contesto",
  ...Array.from({ length: 50 }, (_, i) => `- Regola di contesto ${i + 1}: considera correlazione, settore e liquidità prima di aumentare l'esposizione.`),
].join("\n");

type PromptState = { versions: { version: number; ts: string; actor: string; reason: string; text: string }[] };

function prompts(empty: boolean): Record<string, PromptState> {
  const out: Record<string, PromptState> = {};
  for (const a of AGENTS) {
    const base = a.id === "portfolio_manager" ? LONG_PM : `# ${a.id}\n\nSei ${a.role.toLowerCase()} dell'ufficio.\n\nRispondi in italiano, conciso, citando i dati che usi.\nNon inventare numeri: se un dato manca, dillo.`;
    out[a.id] = { versions: [{ version: 1, ts: ago(60 * DAY), actor: "system", reason: "Default da prompts/", text: base }] };
  }
  if (!empty) {
    const pm = out.portfolio_manager.versions;
    pm.push({ version: 2, ts: ago(12 * DAY), actor: "cockpit", reason: "Più peso alle note di Luca", text: LONG_PM.replace("Leggi le note di Luca prima di decidere.", "Leggi sempre le note di Luca prima di decidere e citale.") });
    pm.push({ version: 3, ts: ago(2 * DAY), actor: "cockpit", reason: "Formato JSON con il campo horizon", text: pm[1].text.replace("decision, size_fraction, reason.", "decision, size_fraction, horizon, reason.") });
    const ta = out.technical_analyst.versions;
    ta.push({ version: 2, ts: ago(5 * DAY), actor: "cockpit", reason: "Chiedo i livelli in tabella", text: ta[0].text + "\nRiporta supporti e resistenze in una tabella con prezzo e forza." });
  }
  return out;
}

type Secret = { name: string; label: string; set: boolean; last4: string | null; updated_ts: string | null; updated_by: string | null; source: "store" | "env" | "none"; test: { ok: boolean; detail: string; ts: string } | null };

function secrets(empty: boolean): Secret[] {
  const none = (name: string, label: string): Secret => ({ name, label, set: false, last4: null, updated_ts: null, updated_by: null, source: "none", test: null });
  if (empty) return [none("OMNIROUTE_API_KEY", "OmniRoute"), none("ALPACA_API_KEY", "Alpaca · key ID"), none("ALPACA_SECRET_KEY", "Alpaca · secret"), none("OPENBB_PAT", "OpenBB"), none("FMP_API_KEY", "Financial Modeling Prep")];
  return [
    { name: "OMNIROUTE_API_KEY", label: "OmniRoute", set: true, last4: "x9Q2", updated_ts: ago(9 * DAY), updated_by: "cockpit", source: "store", test: { ok: true, detail: "14 modelli disponibili", ts: ago(3 * HOUR) } },
    { name: "ALPACA_API_KEY", label: "Alpaca · key ID", set: true, last4: "7KDA", updated_ts: null, updated_by: null, source: "env", test: { ok: true, detail: "Conto PA3X… attivo, buying power $187.420", ts: ago(3 * HOUR) } },
    { name: "ALPACA_SECRET_KEY", label: "Alpaca · secret", set: true, last4: "m2Lp", updated_ts: null, updated_by: null, source: "env", test: { ok: true, detail: "Coppia valida", ts: ago(3 * HOUR) } },
    { name: "OPENBB_PAT", label: "OpenBB", set: true, last4: "Tq81", updated_ts: ago(30 * DAY), updated_by: "cockpit", source: "store", test: { ok: false, detail: "401 Unauthorized: token scaduto", ts: ago(40 * MIN) } },
    none("FMP_API_KEY", "Financial Modeling Prep"),
  ];
}

function makeState(empty: boolean) {
  const sections = defaults();
  const values: Record<string, Val> = {};
  const history: { version: number; ts: string; actor: string; reason: string; changes: { key: string; old: Val; new: Val }[] }[] = [];
  let pending: string[] = [];
  if (!empty) {
    const apply = (version: number, daysAgo: number, reason: string, changes: Record<string, Val>) => {
      const all = sections.flatMap((s) => s.items);
      history.unshift({ version, ts: ago(daysAgo * DAY), actor: "cockpit", reason, changes: Object.entries(changes).map(([key, v]) => ({ key, old: values[key] ?? all.find((i) => i.key === key)!.value, new: v })) });
      Object.assign(values, changes);
    };
    apply(2, 34, "Budget del PM più largo per le giornate di trimestrali", { "agents.portfolio_manager.daily_budget_usd": 12 });
    apply(3, 8, "Cicli più frequenti in apertura", { "schedule.cycle_minutes": 20, max_parallel: 4 });
    apply(4, 0.2, "Provo il proxy locale per gli agenti del ticker", { "agents.ticker_agent.endpoint": "http://127.0.0.1:20129/v1" });
    pending = ["agents.ticker_agent.endpoint"];
  }
  return {
    sections,
    values,
    history,
    pending,
    version: empty ? 1 : 4,
    prompts: prompts(empty),
    secrets: secrets(empty),
    backups: empty ? [] : [
      { name: "office-2026-11-24T03-00.db", ts: ago(9 * HOUR), size_bytes: 1_402_000_000 },
      { name: "office-2026-11-23T03-00.db", ts: ago(33 * HOUR), size_bytes: 1_389_000_000 },
    ],
    started: Date.now() - (2 * DAY + 5 * HOUR),
    empty,
  };
}

let state = makeState(false);

const allItems = () => state.sections.flatMap((s) => s.items);
const current = (i: Item): Val => (i.key in state.values ? state.values[i.key] : i.value);

function settingsRead() {
  const last = state.history[0];
  return {
    version: state.version,
    updated_ts: last?.ts ?? null,
    updated_by: last?.actor ?? null,
    pending_restart: state.pending,
    sections: state.sections.map((s) => ({ id: s.id, title: s.title, items: s.items.map((i) => ({ ...i, value: current(i), overridden: current(i) !== i.default })) })),
  };
}

function agentConfigs() {
  const v = (k: string) => current(allItems().find((i) => i.key === k)!);
  return AGENTS.map((a) => {
    const p = state.prompts[a.id].versions.at(-1)!;
    return { agent: a.id, role: a.role, model: v(`agents.${a.id}.model`), endpoint: v(`agents.${a.id}.endpoint`), effort: v(`agents.${a.id}.effort`), daily_budget_usd: v(`agents.${a.id}.daily_budget_usd`), today_cost: state.empty ? 0 : a.cost, prompt_version: p.version, prompt_updated_ts: p.ts };
  });
}

function validate(i: Item, v: unknown): string | null {
  if (i.type === "int" || i.type === "float") {
    if (typeof v !== "number" || !Number.isFinite(v)) return "Serve un numero";
    if (i.type === "int" && !Number.isInteger(v)) return "Serve un numero intero";
    if (i.min !== null && v < i.min) return `Sotto il minimo ${i.min}`;
    if (i.max !== null && v > i.max) return `Oltre il massimo ${i.max}`;
  } else if (i.type === "enum") {
    if (!i.options?.includes(String(v))) return `Valore non ammesso: ${String(v)}`;
  } else if (i.type === "time") {
    if (typeof v !== "string" || !/^([01]\d|2[0-3]):[0-5]\d$/.test(v)) return "Ora non valida (HH:MM)";
  } else if (i.type === "bool") {
    if (typeof v !== "boolean") return "Serve sì o no";
  } else if (typeof v !== "string" || !v.trim()) return "Valore vuoto";
  return null;
}

function updateSettings(p: Record<string, unknown>) {
  const changes = (p.changes ?? {}) as Record<string, Val>;
  const reason = String(p.reason ?? "").trim();
  const items = allItems();
  const merged = { ...Object.fromEntries(items.map((i) => [i.key, current(i)])), ...changes };
  const rows = Object.entries(changes).map(([key, v]) => {
    const i = items.find((x) => x.key === key);
    if (!i) return { key, old: null, new: v, apply: "live" as const, ok: false, reason: "Chiave sconosciuta" };
    let why = validate(i, v);
    // Cross-field rule only the Runtime can check: the window of scheduled tasks must stay open.
    if (!why && (key === "scheduled_task_min_days" || key === "scheduled_task_max_days") && Number(merged.scheduled_task_min_days) > Number(merged.scheduled_task_max_days)) {
      why = `Il minimo (${merged.scheduled_task_min_days}) supera il massimo (${merged.scheduled_task_max_days})`;
    }
    return { key, old: current(i), new: v, apply: i.apply, ok: !why, reason: why };
  });
  const warnings: string[] = [];
  if ("market.bar_timeframe" in changes) warnings.push("Cambiare il timeframe richiede di ricalibrare i coefficienti k degli indicatori (wiki: market-data/bar-timeframe): fino ad allora i segnali possono cambiare soglia.");
  if (rows.some((r) => r.ok && r.apply === "restart")) warnings.push("Alcune modifiche valgono dal prossimo riavvio del Runtime: fino ad allora resta il valore attuale.");
  const capital = rows.some((r) => items.find((i) => i.key === r.key)?.capital);
  const preview = { changes: rows, warnings };
  if (p.dry_run) return { ok: true, data: preview, reasons: [] };
  const reasons: string[] = [];
  if (reason.length < 5) reasons.push("Il motivo è obbligatorio");
  if (capital && p.confirm !== true) reasons.push("approval_mode tocca il capitale: serve confirm:true");
  for (const r of rows) if (!r.ok) reasons.push(`${r.key}: ${r.reason}`);
  if (!rows.length) reasons.push("Nessuna modifica");
  if (reasons.length) return { ok: false, data: preview, reasons };
  state.version += 1;
  state.history.unshift({ version: state.version, ts: iso(Date.now()), actor: "cockpit", reason, changes: rows.map((r) => ({ key: r.key, old: r.old as Val, new: r.new })) });
  Object.assign(state.values, changes);
  for (const r of rows) if (r.apply === "restart" && !state.pending.includes(r.key)) state.pending.push(r.key);
  return { ok: true, data: preview, reasons: [] };
}

function restoreSettings(p: Record<string, unknown>) {
  const v = Number(p.version);
  const reason = String(p.reason ?? "").trim();
  if (reason.length < 5) return { ok: false, data: {}, reasons: ["Il motivo è obbligatorio"] };
  // Values as they were right after version v: undo every later change, newest first.
  const later = state.history.filter((h) => h.version > v);
  if (!state.history.some((h) => h.version === v) && v !== 1) return { ok: false, data: {}, reasons: [`Versione ${v} sconosciuta`] };
  const target: Record<string, Val> = {};
  for (const h of later) for (const c of h.changes) target[c.key] = c.old;
  const changes = Object.fromEntries(Object.entries(target).filter(([k, val]) => current(allItems().find((i) => i.key === k)!) !== val));
  if (!Object.keys(changes).length) return { ok: false, data: {}, reasons: ["I valori sono già quelli della versione scelta"] };
  return updateSettings({ changes, reason: `Ripristino della versione ${v}: ${reason}`, confirm: true });
}

function promptRead(agent: string) {
  const s = state.prompts[agent];
  if (!s) return null;
  const p = s.versions.at(-1)!;
  return { agent, version: p.version, text: p.text, updated_ts: p.ts, updated_by: p.actor, reason: p.reason, is_default: s.versions.length === 1 };
}

function updatePrompt(p: Record<string, unknown>) {
  const s = state.prompts[String(p.agent)];
  if (!s) return { ok: false, data: {}, reasons: [`Agente sconosciuto: ${String(p.agent)}`] };
  const text = String(p.text ?? "");
  const reason = String(p.reason ?? "").trim();
  const reasons: string[] = [];
  if (!text.trim()) reasons.push("Il prompt non può essere vuoto");
  if (text.length > 60_000) reasons.push("Il prompt supera 60.000 caratteri");
  if (text === s.versions.at(-1)!.text) reasons.push("Il testo è uguale alla versione attiva");
  if (p.dry_run) return { ok: reasons.length === 0, data: { chars_before: s.versions.at(-1)!.text.length, chars_after: text.length }, reasons };
  if (reason.length < 5) reasons.push("Il motivo è obbligatorio");
  if (reasons.length) return { ok: false, data: {}, reasons };
  const version = s.versions.at(-1)!.version + 1;
  s.versions.push({ version, ts: iso(Date.now()), actor: "cockpit", reason, text });
  return { ok: true, data: { version }, reasons: [] };
}

function restorePrompt(p: Record<string, unknown>) {
  const s = state.prompts[String(p.agent)];
  const old = s?.versions.find((v) => v.version === Number(p.version));
  if (!s || !old) return { ok: false, data: {}, reasons: ["Versione sconosciuta"] };
  return updatePrompt({ agent: p.agent, text: old.text, reason: `Ripristino della versione ${old.version}: ${String(p.reason ?? "").trim()}` });
}

function setSecret(p: Record<string, unknown>) {
  const s = state.secrets.find((x) => x.name === p.name);
  const value = typeof p.value === "string" ? p.value : "";
  const reasons: string[] = [];
  if (!s) reasons.push(`Chiave sconosciuta: ${String(p.name)}`);
  if (value.trim().length < 8) reasons.push("La chiave è troppo corta");
  if (String(p.reason ?? "").trim().length < 5) reasons.push("Il motivo è obbligatorio");
  if (s?.name.startsWith("ALPACA") && p.confirm !== true) reasons.push("Le chiavi del broker richiedono confirm:true");
  if (reasons.length || !s) return { ok: false, data: {}, reasons };
  const last4 = value.trim().slice(-4);
  const ok = !value.startsWith("bad");
  Object.assign(s, { set: true, last4, updated_ts: iso(Date.now()), updated_by: "cockpit", source: "store", test: { ok, detail: ok ? "Connessione riuscita" : "401 Unauthorized", ts: iso(Date.now()) } });
  return { ok: true, data: { name: s.name, set: true, last4, test: { ok, detail: s.test!.detail } }, reasons: [] };
}

function clearSecret(p: Record<string, unknown>) {
  const s = state.secrets.find((x) => x.name === p.name);
  if (!s) return { ok: false, data: {}, reasons: ["Chiave sconosciuta"] };
  if (p.confirm !== true) return { ok: false, data: {}, reasons: ["Serve confirm:true"] };
  if (s.source === "env") return { ok: false, data: {}, reasons: ["La chiave arriva dall'ambiente (.env o variabile): toglila da lì e riavvia il Runtime"] };
  Object.assign(s, { set: false, last4: null, updated_ts: iso(Date.now()), updated_by: "cockpit", source: "none", test: null });
  return { ok: true, data: { name: s.name }, reasons: [] };
}

function testConnection(p: Record<string, unknown>) {
  const prefix = { omniroute: "OMNIROUTE", alpaca: "ALPACA", openbb: "OPENBB" }[String(p.target)] ?? "?";
  const keys = state.secrets.filter((s) => s.name.startsWith(prefix));
  if (!keys.length) return { ok: false, data: {}, reasons: ["Target sconosciuto"] };
  // The seeded OpenBB token is the expired one; any key written since tests fine unless it starts with "bad".
  const ok = keys.every((k) => k.set && k.last4 !== "Tq81" && k.test?.detail !== "401 Unauthorized");
  const detail = !keys.every((k) => k.set) ? "Chiave mancante" : ok ? "Connessione riuscita" : "401 Unauthorized: token scaduto";
  for (const k of keys) if (k.set) k.test = { ok, detail, ts: iso(Date.now()) };
  return { ok: true, data: { ok, detail }, reasons: [] };
}

function health() {
  const size = state.empty ? 48_000_000 : 1_342_177_280;
  const v = (k: string) => current(allItems().find((i) => i.key === k)!);
  return {
    version: "0.9.0",
    commit: "85794ff",
    started_ts: iso(state.started),
    uptime_s: Math.round((Date.now() - state.started) / 1000),
    db: { path_label: "data/office.db", size_bytes: size, wal_bytes: state.empty ? 1_200_000 : 96_468_992, alert_mb: v("db_size_alert_mb"), last_backup_ts: state.backups[0]?.ts ?? null },
    jobs: [
      { name: "ticker_cycles", last_run_ts: ago(4 * MIN), last_status: "ok", last_error: null, next_run_ts: iso(Date.now() + 16 * MIN) },
      { name: "news_ingest", last_run_ts: ago(11 * MIN), last_status: state.empty ? "ok" : "error", last_error: state.empty ? null : "Timeout del feed Reuters dopo 30 s (3 tentativi)", next_run_ts: iso(Date.now() + 4 * MIN) },
      { name: "portfolio_sync", last_run_ts: ago(1 * MIN), last_status: "ok", last_error: null, next_run_ts: iso(Date.now() + 1 * MIN) },
      { name: "retention", last_run_ts: ago(21 * HOUR), last_status: "ok", last_error: null, next_run_ts: iso(Date.now() + 3 * HOUR) },
      { name: "backup_db", last_run_ts: state.backups[0]?.ts ?? null, last_status: state.backups.length ? "ok" : null, last_error: null, next_run_ts: iso(Date.now() + 15 * HOUR) },
      { name: "premarket_scan", last_run_ts: null, last_status: null, last_error: null, next_run_ts: iso(Date.now() + 19 * HOUR) },
    ],
    errors: state.empty
      ? []
      : [
          { ts: ago(11 * MIN), source: "news_ingest", message: "Timeout del feed Reuters dopo 30 s (3 tentativi)" },
          { ts: ago(40 * MIN), source: "openbb", message: "401 Unauthorized: token scaduto" },
          { ts: ago(26 * HOUR), source: "broker", message: "Stream Alpaca riconnesso dopo 12 s" },
        ],
    sse_clients: 2,
    broker: { ok: true, detail: "Stream connesso" },
    llm: state.empty ? { ok: false, detail: "OMNIROUTE_API_KEY mancante" } : { ok: true, detail: "OmniRoute risponde in 180 ms" },
  };
}

function backupDb() {
  const ts = Date.now();
  const name = `office-${iso(ts).slice(0, 16).replace(":", "-")}.db`;
  state.backups.unshift({ name, ts: iso(ts), size_bytes: 1_342_177_280 });
  state.backups = state.backups.slice(0, 7);
  return { ok: true, data: { name }, reasons: [] };
}

function readBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      try {
        resolve(JSON.parse(raw || "{}"));
      } catch {
        resolve({});
      }
    });
  });
}

function send(res: ServerResponse, body: unknown) {
  res.setHeader("Content-Type", "application/json");
  res.setHeader("X-Dev-Fixture", "settings");
  res.end(JSON.stringify(body));
}

const COMMANDS: Record<string, (p: Record<string, unknown>) => unknown> = {
  update_settings: updateSettings,
  restore_settings: restoreSettings,
  update_prompt: updatePrompt,
  restore_prompt: restorePrompt,
  set_secret: setSecret,
  clear_secret: clearSecret,
  test_connection: testConnection,
  backup_db: backupDb,
};

export function settingsFixtures(mode: string): Plugin {
  state = makeState(mode === "empty");
  return {
    name: "cockpit-settings-fixtures",
    apply: "serve",
    configureServer(server) {
      server.config.logger.info(`  ⚠ Configurazioni: fixture di sviluppo attive (COCKPIT_SETTINGS_FIXTURES=${mode})`);
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url ?? "/", "http://dev");
        const read = url.pathname.match(/^\/v1\/read\/([a-z_]+)$/)?.[1];
        if (read) {
          const agent = url.searchParams.get("agent") ?? "";
          const limit = Number(url.searchParams.get("limit") ?? 50);
          const reads: Record<string, () => unknown> = {
            settings: settingsRead,
            settings_history: () => state.history.slice(0, limit),
            agent_configs: agentConfigs,
            prompt: () => promptRead(agent),
            prompt_history: () =>
              (state.prompts[agent]?.versions ?? [])
                .slice()
                .reverse()
                .slice(0, limit)
                .map(({ text, ...v }) => ({ ...v, chars: text.length })),
            secrets: () => state.secrets,
            runtime_health: health,
            backups: () => state.backups,
          };
          const fn = reads[read];
          if (!fn) return next();
          const body = fn();
          if (body === null) {
            res.statusCode = 404;
            return send(res, { detail: "Agente sconosciuto" });
          }
          return send(res, body);
        }
        const cmd = url.pathname.match(/^\/v1\/commands\/([a-z_]+)$/)?.[1];
        if (cmd && COMMANDS[cmd] && req.method === "POST") {
          const body = await readBody(req);
          return send(res, COMMANDS[cmd](body));
        }
        next();
      });
    },
  };
}
