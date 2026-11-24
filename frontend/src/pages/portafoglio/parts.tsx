import { CircleAlert, CircleCheck, CircleX, Info, Plug } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { LimitName, LimitStatus, Sourced } from "@/features/portfolio/types";
import { fmtMoney, fmtPct, toNum } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Fraction to percent text: 0.1234 → "12,34%". `sign` adds + on gains. */
export function fmtFrac(v: number | null | undefined, opts: { sign?: boolean; decimals?: number } = {}): string {
  const n = toNum(v);
  if (n === null) return "—";
  const d = opts.decimals ?? 2;
  const p = Math.abs(n * 100);
  const s = new Intl.NumberFormat("it-IT", { minimumFractionDigits: d, maximumFractionDigits: d }).format(p);
  const sign = n < 0 ? "−" : opts.sign && n > 0 ? "+" : "";
  return `${sign}${s}%`;
}

export const fmtRatio = (v: number | null | undefined, d = 2) => {
  const n = toNum(v);
  return n === null ? "—" : new Intl.NumberFormat("it-IT", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n);
};

export const fmtSignedRatio = (v: number | null | undefined) => {
  const n = toNum(v);
  if (n === null) return "—";
  return `${n < 0 ? "−" : n > 0 ? "+" : ""}${fmtRatio(Math.abs(n))}`;
};

/** "3 g 4 h", "6 h", "45 min" */
export function fmtDuration(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h`;
  const d = Math.floor(h / 24);
  const rh = h % 24;
  return rh ? `${d} g ${rh} h` : `${d} g`;
}

export const tone = (v: number | null | undefined) => (v === null || v === undefined || v === 0 ? "text-fg" : v > 0 ? "text-up" : "text-down");

export { fmtMoney, fmtPct };

/** What each Risk Gate limit means, how its value reads, and how it is edited. */
export const LIMIT_META: Record<LimitName, { label: string; hint: string; kind: "fraction" | "count" | "ratio" | "days"; min?: boolean }> = {
  max_risk_per_trade_fraction: { label: "Rischio per trade", hint: "Perdita massima fino allo stop, in % dell'equity", kind: "fraction" },
  max_position_fraction: { label: "Peso per posizione", hint: "Valore massimo di una posizione, in % dell'equity", kind: "fraction" },
  max_sector_fraction: { label: "Esposizione per settore", hint: "Valore massimo per settore, in % dell'equity", kind: "fraction" },
  max_open_positions: { label: "Posizioni aperte", hint: "Numero massimo di posizioni contemporanee", kind: "count" },
  min_cash_reserve_fraction: { label: "Riserva di cassa", hint: "Cassa minima da tenere, in % dell'equity", kind: "fraction", min: true },
  min_risk_reward_ratio: { label: "R:R minimo", hint: "Rapporto rendimento/rischio minimo per aprire", kind: "ratio", min: true },
  earnings_embargo_days: { label: "Embargo trimestrali", hint: "Giorni prima degli utili in cui non si apre", kind: "days" },
};

export function fmtLimit(name: LimitName | string, v: number | null | undefined): string {
  const meta = LIMIT_META[name as LimitName];
  if (v === null || v === undefined) return "—";
  if (!meta) return String(v);
  if (meta.kind === "fraction") return fmtFrac(v, { decimals: v < 0.1 && Math.round(v * 1000) % 10 !== 0 ? 1 : 0 });
  if (meta.kind === "ratio") return fmtRatio(v, 1);
  if (meta.kind === "days") return `${v} ${v === 1 ? "giorno" : "giorni"}`;
  return String(v);
}

export const STATUS_WORD: Record<LimitStatus, string> = { ok: "Entro", near: "Vicino", breach: "Oltre" };

/** The limit's state as one word with an icon: same word and colour in allocation, positions and Rischio e vincoli. */
export function StatusWord({ status, className, compact = false }: { status: LimitStatus; className?: string; compact?: boolean }) {
  const Icon = status === "breach" ? CircleX : status === "near" ? CircleAlert : CircleCheck;
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-5 gap-1 whitespace-nowrap rounded-tag px-1.5 text-2xs font-medium border-transparent",
        status === "breach" ? "bg-down-soft text-down" : status === "near" ? "bg-warn-soft text-warn" : "text-fg-subtle bg-transparent",
        compact && status === "ok" && "px-0",
        className,
      )}
    >
      <Icon className="size-3" strokeWidth={2} aria-hidden />
      {STATUS_WORD[status]}
    </Badge>
  );
}

export function statusFor(value: number | null, limit: number | null, min = false): LimitStatus {
  if (value === null || limit === null) return "ok";
  if (min) return value < limit ? "breach" : value < limit * 1.25 ? "near" : "ok";
  return value > limit + 1e-9 ? "breach" : value >= limit * 0.8 ? "near" : "ok";
}

/**
 * A sunken bar with the limit as a tick: the page's signature. The fill is neutral while inside the limit,
 * warn when near, down when over. `scale` is the value at the right edge, shared by sibling bars.
 */
export function LimitBar({
  value,
  limit,
  scale,
  status,
  min = false,
  className,
  height = 6,
  label,
}: {
  value: number;
  limit: number | null;
  scale: number;
  status: LimitStatus;
  min?: boolean;
  className?: string;
  height?: number;
  label?: string;
}) {
  const w = scale > 0 ? Math.min(100, Math.max(0, (value / scale) * 100)) : 0;
  const t = limit !== null && scale > 0 ? Math.min(100, (limit / scale) * 100) : null;
  return (
    <span className={cn("relative block w-full", className)} role="img" aria-label={label}>
      <span className="block overflow-hidden rounded-tag bg-[oklch(0_0_0/0.32)]" style={{ height }}>
        <span
          className={cn(
            "bar-grow block h-full rounded-tag",
            status === "breach" ? "bg-down" : status === "near" ? "bg-warn" : min ? "bg-fg-subtle" : "bg-[oklch(0.62_0.012_255)]",
          )}
          style={{ width: `${w}%` }}
        />
      </span>
      {t !== null && (
        <span aria-hidden className="absolute -top-[3px] w-[2px] rounded-full bg-fg" style={{ left: `calc(${t}% - 1px)`, height: height + 6 }} />
      )}
    </span>
  );
}

/** Quiet line under a read that was rebuilt or is missing: says where the data comes from. */
export function SourceNote({ sourced, className }: { sourced: Sourced<unknown> | undefined; className?: string }) {
  if (!sourced || sourced.source === "runtime") return null;
  return (
    <p className={cn("flex items-start gap-1.5 text-2xs leading-4 text-fg-subtle", className)}>
      <Info className="mt-px size-3 shrink-0" aria-hidden />
      <span>{sourced.note}</span>
    </p>
  );
}

/** A region with nothing honest to show yet: names the endpoint it waits for. */
export function Unavailable({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start gap-2.5 rounded-control bg-[oklch(0_0_0/0.18)] px-3.5 py-3 text-xs leading-relaxed text-fg-muted", className)}>
      <Plug className="mt-0.5 size-3.5 shrink-0 text-fg-subtle" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function ReadError({ error, what }: { error: Error; what: string }) {
  return (
    <p role="alert" className="px-4 py-6 text-center text-xs text-down">
      {what} non disponibile: {error.message}
    </p>
  );
}

export function Bones({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-busy aria-label="Caricamento">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-6 animate-pulse rounded-item bg-hover" style={{ width: `${92 - i * 9}%` }} />
      ))}
    </div>
  );
}

/** Label over value. `hint` becomes a tooltip; `foot` is a quiet second line (reason when n/d). */
export function Metric({ label, value, foot, hint, valueClass, className }: { label: string; value: ReactNode; foot?: ReactNode; hint?: string; valueClass?: string; className?: string }) {
  const body = (
    <div className={cn("min-w-0", className)}>
      <dt className="truncate text-2xs text-fg-subtle">{label}</dt>
      <dd className={cn("num mt-0.5 truncate text-[13px] font-medium text-fg", valueClass)}>{value}</dd>
      {foot && <dd className="mt-0.5 text-2xs leading-4 text-fg-subtle">{foot}</dd>}
    </div>
  );
  if (!hint) return body;
  return (
    <Tooltip>
      <TooltipTrigger render={body} />
      <TooltipContent className="max-w-64">{hint}</TooltipContent>
    </Tooltip>
  );
}

export function TileTitle({ children, meta, end, className }: { children: ReactNode; meta?: ReactNode; end?: ReactNode; className?: string }) {
  return (
    <header className={cn("flex h-11 shrink-0 items-center gap-2 pl-4 pr-2", className)}>
      <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">{children}</h2>
      {meta && <span className="num min-w-0 truncate text-2xs text-fg-subtle">{meta}</span>}
      {end && <div className="ml-auto flex shrink-0 items-center gap-1">{end}</div>}
    </header>
  );
}
