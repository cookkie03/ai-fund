import { OctagonPause } from "lucide-react";
import type { PortfolioPosition, PortfolioSummary, RiskLimitsRead, Sourced } from "@/features/portfolio/types";
import { fmtAge } from "@/lib/format";
import { cn } from "@/lib/utils";
import { fmtFrac, fmtMoney, Metric, SourceNote, tone } from "./parts";

const STALE_S = 15 * 60;

/** Snapshot age as words: fresh is quiet, old is warn with the age. */
export function Freshness({ summary, now }: { summary: PortfolioSummary | null | undefined; now: number }) {
  if (!summary) return null;
  const ts = Date.parse(summary.ts);
  const age = Number.isFinite(ts) ? Math.max(0, (now - ts) / 1000) : summary.snapshot_age_s;
  if (age === null) return null;
  const stale = age > STALE_S;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-2xs", stale ? "text-warn" : "text-fg-subtle")}>
      <span aria-hidden className={cn("size-1.5 rounded-full", stale ? "bg-warn" : "bg-up")} />
      {stale ? `Snapshot vecchio: ${fmtAge(now - age * 1000, now)} fa` : `Snapshot di ${fmtAge(now - age * 1000, now)} fa`}
    </span>
  );
}

export function HaltBanner({ className }: { className?: string }) {
  return (
    <div role="status" className={cn("flex items-center gap-2.5 rounded-control bg-halt-ground px-4 py-2.5 text-xs text-fg", className)}>
      <OctagonPause className="size-4 shrink-0 text-down" aria-hidden />
      <span>
        <span className="font-semibold">Halt attivo.</span> Chiusure, modifiche di stop e target e approvazioni sono sospese finché il trading non riprende. Le letture restano vere.
      </span>
    </div>
  );
}

/**
 * The statement's head: equity is the page's one large figure, the day change sits on its tint as a tag,
 * then a row of meters, each tied to what it is measured against (reserve, max positions, equity).
 */
export function SummaryBand({
  q,
  positions,
  limits,
  compact = false,
}: {
  q: { data?: Sourced<PortfolioSummary | null>; isPending: boolean; error: Error | null };
  positions: PortfolioPosition[] | null;
  limits: RiskLimitsRead | null;
  compact?: boolean;
}) {
  const s = q.data && q.data.source !== "unavailable" ? q.data.data : null;
  const openRisk = positions ? positions.reduce((a, p) => a + (p.open_risk ?? 0), 0) : null;
  const riskKnown = positions?.some((p) => p.open_risk !== null) ?? false;

  if (q.isPending) {
    return (
      <section aria-label="Riepilogo" aria-busy className="rounded-tile bg-ground p-4">
        <span className="block h-3 w-16 animate-pulse rounded-tag bg-hover" />
        <span className="mt-2 block h-8 w-56 animate-pulse rounded-item bg-hover" />
        <span className="mt-4 block h-8 w-full animate-pulse rounded-item bg-hover" />
      </section>
    );
  }
  if (q.error) {
    return (
      <section aria-label="Riepilogo" className="rounded-tile bg-ground p-4 text-xs text-down">
        Riepilogo non disponibile: {q.error.message}
      </section>
    );
  }
  if (!s) {
    return (
      <section aria-label="Riepilogo" className="rounded-tile bg-ground p-4 text-xs text-fg-muted">
        Nessuno snapshot del portafoglio: il Runtime non ha ancora sincronizzato il conto con il broker.
      </section>
    );
  }

  const dayUp = (s.day_change ?? 0) >= 0;
  const reserveMin = limits?.limits.min_cash_reserve_fraction ?? null;
  const maxPos = limits?.limits.max_open_positions ?? null;
  const reserveLow = reserveMin !== null && s.cash_reserve_fraction !== null && s.cash_reserve_fraction < reserveMin;

  const head = (
    <div className="min-w-0">
      <p className="text-2xs text-fg-subtle">Equity</p>
      <p className="mt-0.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span data-region="equity" className={cn("num font-semibold tracking-[-0.025em] text-fg", compact ? "text-[22px] leading-7" : "text-[30px] leading-9")}>
          {fmtMoney(s.equity)}
        </span>
        {s.day_change !== null ? (
          <span className={cn("num inline-flex h-6 items-center gap-1.5 rounded-tag px-2 text-xs font-medium", dayUp ? "bg-up-soft text-up" : "bg-down-soft text-down")}>
            {fmtMoney(s.day_change, { sign: true })}
            <span className="opacity-80">{fmtFrac(s.day_change_fraction, { sign: true })}</span>
            <span className="font-normal text-fg-muted">oggi</span>
          </span>
        ) : (
          <span className="text-2xs text-fg-subtle">variazione di oggi n/d: manca la chiusura di ieri</span>
        )}
      </p>
    </div>
  );

  const meters = [
    { label: "PnL non realizzato", value: fmtMoney(s.unrealized_pnl, { sign: true }), cls: tone(s.unrealized_pnl), hint: "Somma del PnL aperto delle posizioni ai prezzi correnti" },
    { label: "PnL realizzato oggi", value: fmtMoney(s.realized_pnl_today, { sign: true }), cls: tone(s.realized_pnl_today), hint: "Trade chiusi nella sessione di oggi" },
    { label: "Investito", value: fmtMoney(s.invested, { decimals: 0 }), foot: s.equity ? `${fmtFrac(s.invested / s.equity, { decimals: 1 })} dell'equity` : undefined },
    {
      label: "Cassa",
      value: fmtMoney(s.cash, { decimals: 0 }),
      foot: s.cash_reserve_fraction !== null ? `${fmtFrac(s.cash_reserve_fraction, { decimals: 1 })}${reserveMin !== null ? ` · riserva min ${fmtFrac(reserveMin, { decimals: 0 })}` : ""}` : undefined,
      footCls: reserveLow ? "text-down" : undefined,
    },
    { label: "Posizioni", value: `${s.positions_count}${maxPos !== null ? ` / ${maxPos}` : ""}`, hint: maxPos !== null ? `Massimo ${maxPos} posizioni aperte (Risk Gate)` : undefined },
    {
      label: "Rischio aperto",
      value: riskKnown ? fmtMoney(openRisk, { decimals: 0 }) : "—",
      foot: riskKnown && s.equity ? `${fmtFrac((openRisk ?? 0) / s.equity)} dell'equity` : "stop non noti",
      hint: "Perdita totale se ogni posizione toccasse il suo stop, dai prezzi correnti",
    },
  ];

  const visible = compact ? meters.filter((m) => ["PnL non realizzato", "Cassa", "Investito", "Rischio aperto"].includes(m.label)) : meters;

  return (
    <section aria-label="Riepilogo" data-region="summary" className={cn("rounded-tile bg-ground", compact ? "p-3.5" : "px-5 py-4")}>
      <div className={cn("flex gap-x-10 gap-y-4", compact ? "flex-col" : "flex-wrap items-end")}>
        {head}
        <dl className={cn("grid min-w-0 flex-1 gap-x-6 gap-y-3", compact ? "grid-cols-2" : "grid-cols-3 xl:grid-cols-6")}>
          {visible.map((m) => (
            <Metric key={m.label} label={m.label} value={m.value} valueClass={m.cls} hint={m.hint} foot={m.foot ? <span className={m.footCls}>{m.foot}</span> : undefined} />
          ))}
        </dl>
      </div>
      <SourceNote sourced={q.data} className="mt-3" />
    </section>
  );
}
