const nf = (min: number, max = min) =>
  new Intl.NumberFormat("it-IT", { minimumFractionDigits: min, maximumFractionDigits: max, useGrouping: "always" });

const price2 = nf(2);
const int0 = nf(0);
const pct2 = nf(2);

export function toNum(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export const fmtPrice = (v: unknown) => {
  const n = toNum(v);
  return n === null ? "—" : price2.format(n);
};

export const fmtQty = (v: unknown) => {
  const n = toNum(v);
  return n === null ? "—" : Number.isInteger(n) ? int0.format(n) : nf(0, 4).format(n);
};

export const fmtMoney = (v: unknown, opts: { sign?: boolean; decimals?: number } = {}) => {
  const n = toNum(v);
  if (n === null) return "—";
  const d = opts.decimals ?? 2;
  const s = nf(d).format(Math.abs(n));
  const sign = n < 0 ? "−" : opts.sign && n > 0 ? "+" : "";
  return `${sign}$${s}`;
};

export const fmtPct = (v: unknown, opts: { sign?: boolean } = { sign: true }) => {
  const n = toNum(v);
  if (n === null) return "—";
  const sign = n < 0 ? "−" : opts.sign && n > 0 ? "+" : "";
  return `${sign}${pct2.format(Math.abs(n))}%`;
};

export const fmtSigned = (v: unknown) => {
  const n = toNum(v);
  if (n === null) return "—";
  return `${n < 0 ? "−" : n > 0 ? "+" : ""}${price2.format(Math.abs(n))}`;
};

export const fmtVolume = (v: unknown) => {
  const n = toNum(v);
  if (n === null) return "—";
  if (n >= 1e9) return `${nf(2).format(n / 1e9)} Mrd`;
  if (n >= 1e6) return `${nf(2).format(n / 1e6)} M`;
  if (n >= 1e3) return `${nf(1).format(n / 1e3)} K`;
  return int0.format(n);
};

export function parseTs(ts: string | number | null | undefined): number | null {
  if (ts === null || ts === undefined) return null;
  if (typeof ts === "number") return ts < 1e12 ? ts * 1000 : ts;
  const ms = Date.parse(ts);
  return Number.isFinite(ms) ? ms : null;
}

/** "ora", "45 s", "12 min", "3 h", "2 g" */
export function fmtAge(ms: number | null, now = Date.now()): string {
  if (ms === null) return "—";
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 5) return "ora";
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h`;
  return `${Math.floor(h / 24)} g`;
}

const dtf = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const tf = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" });
const df = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short" });

export function fmtWhen(ts: string | number | null | undefined, now = Date.now()): string {
  const ms = parseTs(ts);
  if (ms === null) return "—";
  const d = new Date(ms);
  if (d.toDateString() === new Date(now).toDateString()) return tf.format(d);
  return dtf.format(d);
}

export const fmtDay = (ts: string | number | null | undefined) => {
  const ms = parseTs(ts);
  return ms === null ? "—" : df.format(new Date(ms));
};

export const fmtDateTime = (ts: string | number | null | undefined) => {
  const ms = parseTs(ts);
  return ms === null ? "—" : dtf.format(new Date(ms));
};
