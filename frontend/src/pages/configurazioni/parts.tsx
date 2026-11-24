import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { SettingItem, SettingValue } from "@/features/settings/types";
import { author, type Author } from "@/lib/authors";
import { fmtAge, parseTs } from "@/lib/format";
import { cn } from "@/lib/utils";

export { Bones, ReadError, SourceNote, Unavailable } from "@/pages/portafoglio/parts";

/** Words for the enum values the office uses; anything else reads as the Runtime sends it. */
const VALUE_WORDS: Record<string, string> = {
  low: "Basso",
  medium: "Medio",
  high: "Alto",
  auto: "Automatica",
  manual: "Sempre manuale",
  manual_above_threshold: "Manuale oltre soglia",
};

export function fmtValue(item: Pick<SettingItem, "type" | "unit">, v: SettingValue): string {
  if (v === null || v === undefined || v === "") return "—";
  if (item.type === "bool") return v === true || v === "true" ? "Sì" : "No";
  if (item.type === "enum" && typeof v === "string") return VALUE_WORDS[v] ?? v;
  if (typeof v === "number") {
    const s = new Intl.NumberFormat("it-IT", { maximumFractionDigits: item.type === "float" ? 2 : 0 }).format(v);
    if (item.unit === "$") return `$${s}`;
    if (item.unit === "%") return `${s}%`;
    if (item.unit === "giorni" && v === 1) return "1 giorno";
    return item.unit ? `${s} ${item.unit}` : s;
  }
  return String(v);
}

/** "7–3650 giorni", "$0–$100", "10–100%": the unit once, after the range. */
export function fmtRange(item: Pick<SettingItem, "type" | "unit" | "min" | "max">): string | null {
  if (item.min === null && item.max === null) return null;
  const bare = { type: item.type, unit: item.unit === "$" ? "$" : null };
  const lo = item.min !== null ? fmtValue(bare, item.min) : "…";
  const hi = item.max !== null ? fmtValue(bare, item.max) : "…";
  const u = item.unit && item.unit !== "$" ? (item.unit === "%" ? "%" : ` ${item.unit}`) : "";
  return `${lo}–${hi}${u}`;
}

export const optionWord = (o: string) => VALUE_WORDS[o] ?? o;

/** "ora", "12 min fa", "3 g fa" */
export function since(ts: string | number | null | undefined, now: number): string {
  const a = fmtAge(parseTs(ts ?? null), now);
  return a === "ora" || a === "—" ? a : `${a} fa`;
}

export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const f = (x: number, d = 1) => new Intl.NumberFormat("it-IT", { maximumFractionDigits: d }).format(x);
  if (n >= 1024 ** 3) return `${f(n / 1024 ** 3, 2)} GB`;
  if (n >= 1024 ** 2) return `${f(n / 1024 ** 2, 0)} MB`;
  if (n >= 1024) return `${f(n / 1024, 0)} kB`;
  return `${n} B`;
}

/** "2 g 5 h", "3 h 12 min", "8 min" */
export function fmtUptime(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (d) return `${d} g ${h % 24} h`;
  if (h) return `${h} h ${m % 60} min`;
  return `${m} min`;
}

/** The agent a configuration row is about; `ticker_agent` is the one configuration shared by every ticker agent. */
export function agentAuthor(id: string): Author {
  if (id === "ticker_agent") return { id, kind: "agent", name: "Agenti del ticker", short: "Ticker", initials: "TK", color: "var(--author-ticker)" };
  return author(id);
}

/** A tile of the section column: ground surface, 44 px header without divider. */
export function Panel({ title, meta, end, children, className, id, ...rest }: { title: ReactNode; meta?: ReactNode; end?: ReactNode; children: ReactNode; className?: string; id?: string } & { "aria-label"?: string }) {
  return (
    <section id={id} aria-label={rest["aria-label"] ?? (typeof title === "string" ? title : undefined)} className={cn("min-w-0 rounded-tile bg-ground", className)}>
      <header className="flex min-h-11 flex-wrap items-center gap-x-2 gap-y-1 py-2 pl-4 pr-2">
        <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">{title}</h2>
        {meta && <span className="num min-w-0 truncate text-2xs text-fg-subtle">{meta}</span>}
        {end && <div className="ml-auto flex shrink-0 items-center gap-1">{end}</div>}
      </header>
      {children}
    </section>
  );
}

/** Small state tag: icon and word, never colour alone. */
export function Tag({ icon: Icon, tone = "neutral", children, title, className }: { icon?: LucideIcon; tone?: "neutral" | "warn" | "down" | "accent"; children: ReactNode; title?: string; className?: string }) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-tag px-1.5 text-2xs font-medium",
        tone === "warn" ? "bg-warn-soft text-warn" : tone === "down" ? "bg-down-soft text-down" : tone === "accent" ? "bg-accent-soft text-accent-c" : "bg-hover text-fg-muted",
        className,
      )}
    >
      {Icon && <Icon className="size-3" strokeWidth={2} aria-hidden />}
      {children}
    </span>
  );
}

export const fieldClass =
  "h-8 w-full rounded-control border border-line-strong bg-ground px-2.5 text-sm text-fg outline-none transition-colors placeholder:text-fg-subtle focus:border-accent-c focus-visible:ring-2 focus-visible:ring-ring/40 disabled:opacity-50";
