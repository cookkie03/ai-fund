import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  createChart,
  LineSeries,
  LineStyle,
  TickMarkType,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import { onRadioKeys } from "@/pages/ufficio/parts";
import { periodStart } from "@/features/portfolio/api";
import { useBenchmark, useEquityCurve } from "@/features/portfolio/hooks";
import { PERIOD_LABEL, PERIODS, type EquityPointDD, type Period } from "@/features/portfolio/types";
import { cssColor, withAlpha } from "@/lib/authors";
import { cn } from "@/lib/utils";
import { fmtFrac, fmtMoney, TileTitle } from "./parts";

type Pt = { time: UTCTimestamp; equity: number; ret: number; dd: number | null; spy: number | null };

const fDay = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short" });
const fMonth = new Intl.DateTimeFormat("it-IT", { month: "short" });
const fYear = new Intl.DateTimeFormat("it-IT", { year: "numeric" });
const fFull = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric" });
const money0 = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0, useGrouping: "always" });
const pct1 = new Intl.NumberFormat("it-IT", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** Points of the period, one per timestamp, each indexed to the period's first equity and first SPY close. */
function buildPoints(points: EquityPointDD[], spy: { time: number; close: number }[] | null, period: Period): Pt[] {
  const start = periodStart(period);
  const inRange = points.filter((p) => start === null || Date.parse(p.ts) >= start);
  const byTime = new Map<number, EquityPointDD>();
  for (const p of inRange) {
    const t = Math.floor(Date.parse(p.ts) / 1000);
    if (Number.isFinite(t)) byTime.set(t, p);
  }
  const sorted = [...byTime].sort((a, b) => a[0] - b[0]);
  if (!sorted.length) return [];
  const base = sorted[0][1].equity;
  const spyIn = (spy ?? []).filter((b) => b.time >= sorted[0][0] - 86_400 * 4).sort((a, b) => a.time - b.time);
  const spyBase = spyIn[0]?.close ?? null;
  let j = 0;
  return sorted.map(([t, p]) => {
    while (j + 1 < spyIn.length && spyIn[j + 1].time <= t) j++;
    const close = spyIn[j] && spyIn[j].time <= t + 86_400 ? spyIn[j].close : null;
    return {
      time: t as UTCTimestamp,
      equity: p.equity,
      ret: base ? p.equity / base - 1 : 0,
      dd: p.drawdown_fraction,
      spy: spyBase && close !== null ? close / spyBase - 1 : null,
    };
  });
}

/** The canvas has no text: this is what a screen reader hears instead of the curve. */
function chartSummary(pts: Pt[], period: Period, withSpy: boolean): string {
  const last = pts[pts.length - 1];
  if (!last) return "Curva dell'equity";
  const worst = pts.reduce((m, p) => (p.dd !== null && p.dd < m ? p.dd : m), 0);
  const spy = withSpy && last.spy !== null ? `, SPY ${fmtFrac(last.spy, { sign: true })}` : "";
  return `Curva dell'equity, periodo ${PERIOD_LABEL[period]}: ${fmtMoney(last.equity)}, ${fmtFrac(last.ret, { sign: true })} dal ${fDay.format(new Date((pts[0].time as number) * 1000))}${spy}, drawdown massimo ${fmtFrac(worst)}.`;
}

function palette() {
  return {
    ground: cssColor("var(--ground)"),
    line: cssColor("var(--line)"),
    fg: cssColor("var(--fg)"),
    fgSubtle: cssColor("var(--fg-subtle)"),
    raised: cssColor("var(--raised)"),
    up: cssColor("var(--up)"),
    down: cssColor("var(--down)"),
    system: cssColor("var(--author-system)"),
  };
}

/**
 * Equity over the period, quiet like the Terminale's chart: no grid, solid 1 px crosshair. Alone it reads in
 * dollars; with SPY both series are indexed to 0% at the period start, so one axis carries both (never two
 * scales). Drawdown sits in its own pane underneath. The legend follows the crosshair.
 */
export function EquityChart({ period, onPeriod, className, height = 300, compact = false }: { period: Period; onPeriod: (p: Period) => void; className?: string; height?: number; compact?: boolean }) {
  const [withSpy, setWithSpy] = useState(false);
  const equity = useEquityCurve();
  const bench = useBenchmark(true);
  const spyAvailable = (bench.data?.length ?? 0) > 1;
  const showSpy = withSpy && spyAvailable;
  const pts = useMemo(() => buildPoints(equity.data ?? [], showSpy ? (bench.data ?? []) : null, period), [equity.data, bench.data, showSpy, period]);
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [hover, setHover] = useState<Pt | null>(null);
  const last = pts[pts.length - 1] ?? null;
  const shown = hover ?? last;
  const periodUp = (last?.ret ?? 0) >= 0;
  const enough = pts.length >= 2;
  const hasDd = pts.some((x) => x.dd !== null);
  const series = useRef<{ primary: ISeriesApi<"Area"> | ISeriesApi<"Line">; spy: ISeriesApi<"Line"> | null; dd: ISeriesApi<"Area"> | null } | null>(null);
  const byTime = useRef(new Map<number, Pt>());

  useEffect(() => {
    const el = host.current;
    if (!el || !enough) return;
    const p = palette();
    const main = periodUp ? p.up : p.down;
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: p.ground },
        textColor: p.fgSubtle,
        fontFamily: "'Inter Variable', ui-sans-serif, system-ui, sans-serif",
        fontSize: 11,
        attributionLogo: false,
        panes: { separatorColor: withAlpha(p.line, 0.6), separatorHoverColor: withAlpha(p.line, 0.6), enableResize: false },
      },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: withAlpha(p.fgSubtle, 0.45), width: 1, style: LineStyle.Solid, labelBackgroundColor: p.raised },
        horzLine: { color: withAlpha(p.fgSubtle, 0.45), width: 1, style: LineStyle.Solid, labelBackgroundColor: p.raised },
      },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.16, bottom: 0.12 } },
      timeScale: {
        borderVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
        lockVisibleTimeRangeOnResize: true,
        tickMarkFormatter: (t: Time, type: TickMarkType) => {
          if (typeof t !== "number") return String(t);
          const d = new Date(t * 1000);
          if (type === TickMarkType.Year) return fYear.format(d);
          if (type === TickMarkType.Month) return fMonth.format(d);
          return fDay.format(d);
        },
      },
      localization: {
        locale: "it-IT",
        timeFormatter: (t: Time) => (typeof t === "number" ? fFull.format(new Date(t * 1000)) : String(t)),
      },
      handleScroll: false,
      handleScale: false,
    });
    chartRef.current = chart;

    // Formats live on each series: a chart-wide priceFormatter would also relabel the drawdown pane.
    const pctFmt = { type: "custom" as const, minMove: 0.01, formatter: (v: number) => `${v >= 0 ? "+" : "−"}${pct1.format(Math.abs(v))}%` };
    const moneyFmt = { type: "custom" as const, minMove: 1, formatter: (v: number) => `$${money0.format(v)}` };
    let primary: ISeriesApi<"Area"> | ISeriesApi<"Line">;
    let spySeries: ISeriesApi<"Line"> | null = null;
    let dd: ISeriesApi<"Area"> | null = null;
    if (showSpy) {
      spySeries = chart.addSeries(LineSeries, { color: p.system, lineWidth: 1, lineStyle: LineStyle.Dashed, priceFormat: pctFmt, priceLineVisible: false, lastValueVisible: true, crosshairMarkerRadius: 3, title: "SPY" });
      primary = chart.addSeries(LineSeries, { color: main, lineWidth: 2, priceFormat: pctFmt, priceLineVisible: false, crosshairMarkerRadius: 4, crosshairMarkerBorderColor: p.ground, title: "Portafoglio" });
      primary.createPriceLine({ price: 0, color: withAlpha(p.fgSubtle, 0.35), lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false });
    } else {
      primary = chart.addSeries(AreaSeries, {
        lineColor: main,
        lineWidth: 2,
        topColor: withAlpha(main, 0.16),
        bottomColor: withAlpha(main, 0),
        priceFormat: moneyFmt,
        priceLineVisible: false,
        crosshairMarkerRadius: 4,
        crosshairMarkerBorderColor: p.ground,
      });
    }

    if (hasDd) {
      dd = chart.addSeries(
        AreaSeries,
        {
          lineColor: withAlpha(p.down, 0.7),
          lineWidth: 1,
          topColor: withAlpha(p.down, 0.04),
          bottomColor: withAlpha(p.down, 0.22),
          invertFilledArea: true,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
          priceFormat: { type: "custom", formatter: (v: number) => `${v < 0 ? "−" : ""}${pct1.format(Math.abs(v))}%`, minMove: 0.01 },
        },
        1,
      );
      dd.priceScale().applyOptions({ scaleMargins: { top: 0.32, bottom: 0.06 } });
      chart.panes()[1]?.setStretchFactor(0.34);
      chart.panes()[0]?.setStretchFactor(1);
    }
    series.current = { primary, spy: spySeries, dd };

    const onMove = (param: MouseEventParams) => {
      setHover(typeof param.time === "number" ? (byTime.current.get(param.time) ?? null) : null);
    };
    chart.subscribeCrosshairMove(onMove);
    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
      chartRef.current = null;
      series.current = null;
      setHover(null);
    };
  }, [showSpy, periodUp, enough, hasDd]);

  // Live refetches only replace the data: the chart, its crosshair and its scales stay put.
  useEffect(() => {
    const s = series.current;
    if (!s || !chartRef.current) return;
    byTime.current = new Map(pts.map((x) => [x.time as number, x]));
    if (s.spy) s.spy.setData(pts.filter((x) => x.spy !== null).map((x) => ({ time: x.time, value: (x.spy ?? 0) * 100 })));
    s.primary.setData(pts.map((x) => ({ time: x.time, value: s.spy ? x.ret * 100 : x.equity })));
    if (s.dd) s.dd.setData(pts.filter((x) => x.dd !== null).map((x) => ({ time: x.time, value: (x.dd ?? 0) * 100 })));
    // Scroll and zoom are off, so the whole period always fits, new points included.
    chartRef.current.timeScale().fitContent();
  }, [pts, showSpy, periodUp, hasDd, enough]);

  const firstTs = pts[0]?.time;
  const periods = (
    <div role="radiogroup" aria-label="Periodo" className={cn("seg", compact && "flex w-full")} onKeyDown={onRadioKeys}>
      {PERIODS.map((p) => (
        <button key={p} type="button" role="radio" aria-checked={period === p} tabIndex={period === p ? 0 : -1} onClick={() => onPeriod(p)} className={cn("seg-item px-2", compact && "flex-1 justify-center")}>
          {PERIOD_LABEL[p]}
        </button>
      ))}
    </div>
  );

  return (
    <section aria-label="Andamento dell'equity" data-region="equity-curve" className={cn("flex min-w-0 flex-col rounded-tile bg-ground", className)}>
      <TileTitle
        end={
          <>
            <button
              type="button"
              aria-pressed={withSpy}
              onClick={() => setWithSpy((v) => !v)}
              title={spyAvailable ? "Confronta con SPY, entrambi indicizzati a 0% all'inizio del periodo" : "Il Runtime non ha barre giornaliere di SPY"}
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-control px-2.5 text-xs font-medium transition-colors duration-150",
                withSpy ? "bg-raised text-fg shadow-[0_1px_2px_oklch(0_0_0/0.45),inset_0_0.5px_0_oklch(1_0_0/0.08)]" : "text-fg-subtle hover:bg-hover hover:text-fg",
              )}
            >
              <span aria-hidden className="w-3 border-t border-dashed border-[var(--author-system)]" />
              SPY
            </button>
            {!compact && periods}
          </>
        }
      >
        Andamento
      </TileTitle>
      {compact && <div className="px-2 pb-2">{periods}</div>}

      <div className="num flex min-h-5 flex-wrap items-baseline gap-x-4 gap-y-0.5 px-4 pb-1 text-xs" aria-live="off">
        {shown ? (
          <>
            <span className="text-fg-subtle">{fFull.format(new Date((shown.time as number) * 1000))}</span>
            <span className="text-fg">{fmtMoney(shown.equity)}</span>
            <span className={shown.ret >= 0 ? "text-up" : "text-down"}>
              {fmtFrac(shown.ret, { sign: true })} <span className="text-fg-subtle">dal {firstTs ? fDay.format(new Date((firstTs as number) * 1000)) : "—"}</span>
            </span>
            {showSpy && (
              <span className="text-fg-muted">
                SPY {fmtFrac(shown.spy, { sign: true })}
                {shown.spy !== null && <span className={cn("ml-1.5", shown.ret - shown.spy >= 0 ? "text-up" : "text-down")}>({fmtFrac(shown.ret - shown.spy, { sign: true })} vs SPY)</span>}
              </span>
            )}
            {shown.dd !== null && (
              <span className="text-fg-muted">
                Drawdown <span className={shown.dd < 0 ? "text-down" : "text-fg"}>{fmtFrac(shown.dd)}</span>
              </span>
            )}
          </>
        ) : null}
      </div>

      <div className="relative mx-1 mb-2 min-h-0 flex-1" style={{ minHeight: height }}>
        {equity.isPending ? (
          <div className="absolute inset-3 animate-pulse rounded-item bg-hover/60" aria-busy aria-label="Caricamento della curva" />
        ) : equity.isError ? (
          <p className="absolute inset-0 grid place-items-center text-xs text-down">Storico dell'equity non disponibile: {equity.error.message}</p>
        ) : !enough ? (
          <p className="absolute inset-0 grid place-items-center px-6 text-center text-xs leading-relaxed text-fg-subtle">
            Storico troppo corto per {PERIOD_LABEL[period]}: servono almeno 2 punti di equity nel periodo (ora {pts.length}). Il Runtime ne salva uno a ogni sincronizzazione.
          </p>
        ) : (
          <div ref={host} className="absolute inset-0" role="img" aria-label={chartSummary(pts, period, showSpy)} />
        )}
      </div>
      {withSpy && !spyAvailable && !bench.isPending && <p className="px-4 pb-3 text-2xs text-fg-subtle">Benchmark non disponibile: il Runtime non ha barre giornaliere di SPY.</p>}
    </section>
  );
}
