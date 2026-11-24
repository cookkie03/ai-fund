import { motion } from "motion/react";
import type { ReactNode } from "react";
import { AuthorChip } from "@/components/author-chip";
import { barTransition } from "@/lib/motion";
import { Card } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAttribution, usePerformance } from "@/features/portfolio/hooks";
import { PERIOD_LABEL, PERIODS, type Performance, type Period } from "@/features/portfolio/types";
import { author } from "@/lib/authors";
import { cn } from "@/lib/utils";
import { onRadioKeys } from "@/pages/ufficio/parts";
import { Bones, fmtFrac, fmtMoney, fmtRatio, fmtSignedRatio, Metric, SourceNote, tone, Unavailable } from "./parts";

const fDayYear = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", year: "numeric" });
const fDayOnly = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short" });
/** "21 nov 2025 → 22 nov 2026" when the window crosses a year, "3 set → 22 nov" otherwise. */
function fmtRange(from: string, to: string | null): string {
  const a = new Date(from);
  const b = to ? new Date(to) : new Date();
  if (Number.isNaN(a.getTime())) return "—";
  const f = a.getFullYear() !== b.getFullYear() ? fDayYear : fDayOnly;
  return `${f.format(a)} → ${f.format(b)}`;
}

type Key = keyof Performance;

/** A metric the Runtime may withhold: when null, say why (the `insufficient` reason) instead of a number. */
function M({ perf, k, label, value, valueClass, hint }: { perf: Performance; k: Key; label: string; value: string; valueClass?: string; hint?: string }) {
  const v = perf[k];
  const why = v === null ? perf.insufficient.find((i) => i.metric === k) : undefined;
  return (
    <Metric
      label={label}
      value={v === null ? <span className="text-fg-subtle">n/d</span> : value}
      valueClass={v === null ? undefined : valueClass}
      hint={hint}
      foot={why ? why.reason : undefined}
    />
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <h4 className="mb-2.5 text-2xs font-medium text-fg-muted">{title}</h4>
      <dl className="grid grid-cols-2 gap-x-5 gap-y-3.5">{children}</dl>
    </div>
  );
}

export function PeriodControl({ period, onPeriod }: { period: Period; onPeriod: (p: Period) => void }) {
  return (
    <div role="radiogroup" aria-label="Periodo" className="seg" onKeyDown={onRadioKeys}>
      {PERIODS.map((p) => (
        <button key={p} type="button" role="radio" aria-checked={period === p} tabIndex={period === p ? 0 : -1} onClick={() => onPeriod(p)} className="seg-item px-2">
          {PERIOD_LABEL[p]}
        </button>
      ))}
    </div>
  );
}

/** Diverging bars around zero: gains right in up, losses left in down; label and value in text ink. */
function Contribution({ rows, empty }: { rows: { key: string; label: ReactNode; pnl: number; frac: number; extra?: string }[]; empty: ReactNode }) {
  if (!rows.length) return <div className="px-1 py-2">{empty}</div>;
  const max = Math.max(...rows.map((r) => Math.abs(r.frac)), 1e-6);
  return (
    <ul className="space-y-px">
      {rows.map((r) => {
        const w = (Math.abs(r.frac) / max) * 50;
        const tip = `${fmtMoney(r.pnl, { sign: true })} · ${fmtFrac(r.frac, { sign: true })} del rendimento${r.extra ? ` · ${r.extra}` : ""}`;
        return (
          <Tooltip key={r.key}>
            <TooltipTrigger
              render={
                <li tabIndex={0} className="grid grid-cols-[7rem_1fr_4.5rem] items-center gap-2.5 rounded-item px-2 py-1.5 outline-none hover:bg-hover focus-visible:ring-2 focus-visible:ring-ring/60">
                  <span className="min-w-0 truncate text-xs text-fg">{r.label}</span>
                  <span className="relative h-2" role="img" aria-label={tip}>
                    <span aria-hidden className="absolute inset-y-[-3px] left-1/2 w-px bg-line-strong" />
                    <motion.span
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={barTransition}
                      className={cn("absolute inset-y-0 rounded-tag", r.pnl >= 0 ? "bg-up" : "bg-down")}
                      style={r.pnl >= 0 ? { left: "50%", width: `${w}%`, transformOrigin: "left" } : { right: "50%", width: `${w}%`, transformOrigin: "right" }}
                    />
                  </span>
                  <span className={cn("num text-right text-xs", tone(r.pnl))}>{fmtMoney(r.pnl, { sign: true, decimals: 0 })}</span>
                </li>
              }
            />
            <TooltipContent side="left">{tip}</TooltipContent>
          </Tooltip>
        );
      })}
    </ul>
  );
}

function Attribution({ period }: { period: Period }) {
  const q = useAttribution(period);
  const a = q.data && q.data.source !== "unavailable" ? q.data.data : null;
  const waits = (what: string) => (
    <Unavailable>
      {what} arriva con <span className="num text-fg">/v1/read/attribution</span>.
    </Unavailable>
  );
  return (
    <Card aria-label="Attribuzione" className="m-4 rounded-tile border-line-strong/60 bg-ground p-4 shadow-sm">
      <h3 className="text-xs font-semibold text-fg">Attribuzione del rendimento</h3>
      <p className="mt-0.5 text-2xs text-fg-subtle">Contributo al rendimento del periodo, realizzato e aperto.</p>
      {q.isPending ? (
        <Bones rows={4} className="mt-3" />
      ) : q.isError ? (
        <p className="mt-3 text-xs text-down">Attribuzione non disponibile: {q.error.message}</p>
      ) : a ? (
        <div className="mt-3 grid gap-x-8 gap-y-5 lg:grid-cols-3">
          <div className="min-w-0">
            <h4 className="mb-1.5 px-2 text-2xs font-medium text-fg-muted">Per posizione</h4>
            <Contribution rows={a.by_position.map((r) => ({ key: r.ticker, label: <span className="font-semibold">{r.ticker}</span>, pnl: r.pnl, frac: r.contribution_fraction }))} empty={<p className="text-xs text-fg-subtle">Nessun PnL nel periodo.</p>} />
          </div>
          <div className="min-w-0">
            <h4 className="mb-1.5 px-2 text-2xs font-medium text-fg-muted">Per settore</h4>
            <Contribution rows={a.by_sector.map((r) => ({ key: r.sector, label: r.sector, pnl: r.pnl, frac: r.contribution_fraction }))} empty={waits("Il contributo per settore")} />
          </div>
          <div className="min-w-0">
            <h4 className="mb-1.5 px-2 text-2xs font-medium text-fg-muted">Per agente proponente</h4>
            <Contribution
              rows={a.by_agent.map((r) => ({
                key: r.agent,
                label: (
                  <span className="inline-flex min-w-0 items-center gap-1.5">
                    {r.agent === "unknown" || r.agent === "sconosciuto" ? <span className="text-fg-subtle">Non noto</span> : <><AuthorChip actor={r.agent} size="xs" /><span className="truncate">{author(r.agent).short}</span></>}
                  </span>
                ),
                pnl: r.pnl,
                frac: r.contribution_fraction,
                extra: `${r.trades} trade`,
              }))}
              empty={waits("Il contributo per agente")}
            />
          </div>
        </div>
      ) : null}
      <SourceNote sourced={q.data} className="mt-3" />
    </Card>
  );
}

export function PerformancePanel({ period, onPeriod, mobile }: { period: Period; onPeriod: (p: Period) => void; mobile: boolean }) {
  const q = usePerformance(period);
  const perf = q.data && q.data.source !== "unavailable" ? q.data.data : null;
  const bm = perf?.benchmark ?? null;
  const excess = perf && bm && perf.return_fraction !== null && bm.return_fraction !== null ? perf.return_fraction - bm.return_fraction : null;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 px-4 pb-1 pt-2">
        <p className="num text-2xs text-fg-subtle">
          {perf ? (perf.from ? `${fmtRange(perf.from, perf.to)} · ${perf.observations} osservazioni · ${perf.trades_closed} trade chiusi` : "Nessuna osservazione nel periodo") : " "}
        </p>
        <div className={cn(!mobile && "ml-auto", mobile && "w-full overflow-x-auto")}>
          <PeriodControl period={period} onPeriod={onPeriod} />
        </div>
      </div>
      {q.isPending ? (
        <Bones rows={4} className="p-4" />
      ) : q.isError ? (
        <p className="px-4 py-6 text-xs text-down">Performance non disponibile: {q.error.message}</p>
      ) : perf ? (
        <div className={cn("grid gap-x-10 gap-y-6 px-4 pb-4 pt-3 transition-opacity", q.isPlaceholderData && "opacity-60", mobile ? "grid-cols-1" : "grid-cols-2 xl:grid-cols-4")}>
          <Group title="Rendimento">
            <M perf={perf} k="return_fraction" label={`Rendimento ${PERIOD_LABEL[period]}`} value={fmtFrac(perf.return_fraction, { sign: true })} valueClass={tone(perf.return_fraction)} />
            <Metric
              label={`SPY ${PERIOD_LABEL[period]}`}
              value={bm ? fmtFrac(bm.return_fraction, { sign: true }) : <span className="text-fg-subtle">n/d</span>}
              foot={bm ? (excess !== null ? <span className={tone(excess)}>{fmtFrac(excess, { sign: true })} di differenza</span> : undefined) : "Benchmark non disponibile: mancano le barre di SPY"}
            />
            <M perf={perf} k="realized_pnl" label="PnL realizzato" value={fmtMoney(perf.realized_pnl, { sign: true })} valueClass={tone(perf.realized_pnl)} />
            <M perf={perf} k="unrealized_pnl" label="PnL non realizzato" value={fmtMoney(perf.unrealized_pnl, { sign: true })} valueClass={tone(perf.unrealized_pnl)} />
          </Group>
          <Group title="Rischio">
            <M perf={perf} k="max_drawdown_fraction" label="Max drawdown" value={fmtFrac(perf.max_drawdown_fraction)} valueClass={tone(perf.max_drawdown_fraction)} />
            <M perf={perf} k="current_drawdown_fraction" label="Drawdown attuale" value={fmtFrac(perf.current_drawdown_fraction)} valueClass={tone(perf.current_drawdown_fraction)} />
            <M perf={perf} k="volatility_annualized" label="Volatilità annua" value={fmtFrac(perf.volatility_annualized, { decimals: 1 })} hint="Deviazione standard dei rendimenti giornalieri × √252" />
            <Metric
              label="Beta / correlazione SPY"
              value={bm && (bm.beta !== null || bm.correlation !== null) ? `${fmtRatio(bm.beta)} / ${fmtRatio(bm.correlation)}` : <span className="text-fg-subtle">n/d</span>}
              foot={!bm || bm.beta === null ? (perf.insufficient.find((i) => i.metric === "beta")?.reason ?? "Arriva con /v1/read/performance") : undefined}
            />
          </Group>
          <Group title="Rendimento per rischio">
            <M perf={perf} k="sharpe" label="Sharpe" value={fmtRatio(perf.sharpe)} hint="Rendimento medio annualizzato / volatilità; risk-free 0" />
            <M perf={perf} k="sortino" label="Sortino" value={fmtRatio(perf.sortino)} hint="Come Sharpe, con la sola volatilità negativa" />
          </Group>
          <Group title="Trade">
            <M perf={perf} k="win_rate" label="Win rate" value={fmtFrac(perf.win_rate, { decimals: 0 })} />
            <M perf={perf} k="profit_factor" label="Profit factor" value={fmtRatio(perf.profit_factor)} hint="Somma dei guadagni / somma delle perdite" />
            <M perf={perf} k="expectancy" label="Expectancy" value={fmtMoney(perf.expectancy, { sign: true })} valueClass={tone(perf.expectancy)} hint="PnL medio per trade chiuso" />
            <M perf={perf} k="expectancy_r" label="Expectancy in R" value={`${fmtSignedRatio(perf.expectancy_r)} R`} valueClass={tone(perf.expectancy_r)} hint="R multiplo medio: PnL / rischio iniziale allo stop" />
          </Group>
        </div>
      ) : null}
      <SourceNote sourced={q.data} className="px-4 pb-2" />
      <div className="mx-4 border-t border-line/70" />
      <Attribution period={period} />
    </div>
  );
}
