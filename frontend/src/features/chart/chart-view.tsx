import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  TickMarkType,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LogicalRange,
  type MouseEventParams,
  type SeriesType,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { DrawingManager, type Drawing, type DrawingKind } from "lightweight-charts-drawing";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { author as resolveAuthor, cssColor, withAlpha } from "@/lib/authors";
import { fmtPrice, fmtSigned, fmtVolume } from "@/lib/format";
import type { Bar, IndicatorsResponse } from "@/lib/runtime/types";
import { cn } from "@/lib/utils";

/**
 * The chart's look (Legend): no grid, thin solid strokes, monogram-only labels on the canvas
 * (the text lives in the Disegni tab), quiet order marks and volume, so the candles lead.
 */
const look = {
  grid: "none" as "full" | "horz" | "none",
  gridAlpha: 0,
  crosshair: LineStyle.Solid,
  drawingWidth: 1.5,
  dashedLevels: false,
  fullLabels: false,
  markStyle: LineStyle.Solid,
  markAlpha: 0.5,
  volumeAlpha: 0.12,
  rsiGuides: true,
  barSpacing: 8,
  priceScaleBorder: false,
};
import { INDICATORS, pointCount, type ChartDrawing, type IndicatorId } from "./chart-state";

export type PriceMark = { id: string; price: number; title: string; tone: "entry" | "tp" | "sl" | "pending" | "trail" };

export type ChartViewProps = {
  symbol: string;
  timeframe: string;
  bars: Bar[];
  indicators?: IndicatorsResponse;
  enabled: IndicatorId[];
  drawings: ChartDrawing[];
  hiddenAuthors: string[];
  highlightAuthor: string | null;
  focusDrawing: { id: string; nonce: number } | null;
  marks: PriceMark[];
  tool: DrawingKind | null;
  interactive: boolean;
  onToolChange: (kind: DrawingKind | null) => void;
  onCreate: (d: Pick<ChartDrawing, "id" | "kind" | "points">) => void;
  onUpdate: (d: Pick<ChartDrawing, "id" | "kind" | "points">) => void;
  onRemove: (id: string) => void;
  className?: string;
  children?: React.ReactNode;
};

const ny = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("it-IT", { timeZone: "America/New_York", ...opts });
const fTime = ny({ hour: "2-digit", minute: "2-digit" });
const fDay = ny({ day: "numeric", month: "short" });
const fMonth = ny({ month: "short" });
const fYear = ny({ year: "numeric" });
const fFull = ny({ weekday: "short", day: "2-digit", month: "short", year: "2-digit", hour: "2-digit", minute: "2-digit" });
const fFullDay = ny({ weekday: "short", day: "2-digit", month: "short", year: "numeric" });
const priceFmt = new Intl.NumberFormat("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: "always" });

const INDICATOR_COLORS: Record<string, string> = {
  ema20: "#ebb25f",
  sma50: "#b093e5",
  rsi14: "#ba9cef",
  atr14: "#5ecad7",
  macd_line: "#5ca9f9",
  macd_signal: "#ebb25f",
};

type Palette = ReturnType<typeof readPalette>;

function readPalette() {
  return {
    ground: cssColor("var(--ground)"),
    line: cssColor("var(--line)"),
    lineStrong: cssColor("var(--line-strong)"),
    fgSubtle: cssColor("var(--fg-subtle)"),
    fgMuted: cssColor("var(--fg-muted)"),
    raised: cssColor("var(--raised)"),
    up: cssColor("var(--up)"),
    down: cssColor("var(--down)"),
    accent: cssColor("var(--accent-c)"),
    warn: cssColor("var(--warn)"),
  };
}

function toolHintFor(kind: DrawingKind | null): string | null {
  if (!kind) return null;
  const n = pointCount(kind);
  return n === 1 ? "Clicca sul grafico per posare il disegno · Esc annulla" : `Clicca ${n} punti sul grafico · Esc annulla`;
}

export function ChartView(props: ChartViewProps) {
  const { symbol, timeframe, bars, indicators, enabled, drawings, hiddenAuthors, highlightAuthor, focusDrawing, marks, tool, interactive } = props;
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const indicatorSeries = useRef(new Map<string, ISeriesApi<SeriesType>>());
  const managerRef = useRef<DrawingManager | null>(null);
  const applying = useRef(false);
  const pendingUpdates = useRef(new Map<string, Drawing>());
  const priceLines = useRef<IPriceLine[]>([]);
  const loadedKey = useRef<string | null>(null);
  const paletteRef = useRef<Palette | null>(null);
  const cbRef = useRef(props);
  cbRef.current = props;

  const [hover, setHover] = useState<number | null>(null);
  const [paneTops, setPaneTops] = useState<{ id: string; top: number }[]>([]);
  const paneIdsRef = useRef<string[]>([]);
  const measurePanes = useCallback(() => {
    const chart = chartRef.current;
    const ids = paneIdsRef.current;
    if (!chart || !ids.length) return;
    let y = 0;
    const out: { id: string; top: number }[] = [];
    chart.panes().forEach((pn, i) => {
      if (i > 0 && ids[i - 1]) out.push({ id: ids[i - 1], top: y + 4 });
      y += pn.getHeight() + 1;
    });
    setPaneTops((prev) => (prev.length === out.length && prev.every((p, i) => p.id === out[i].id && p.top === out[i].top) ? prev : out));
  }, []);
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const ro = new ResizeObserver(() => requestAnimationFrame(measurePanes));
    ro.observe(host);
    return () => ro.disconnect();
  }, [measurePanes]);

  const intraday = timeframe !== "1d";

  // ---- create once -------------------------------------------------------------------------
  useEffect(() => {
    const host = hostRef.current!;
    const p = readPalette();
    paletteRef.current = p;
    const chart = createChart(host, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: p.ground },
        textColor: p.fgSubtle,
        fontFamily: "'Inter Variable', ui-sans-serif, system-ui, sans-serif",
        fontSize: 11,
        attributionLogo: true,
        panes: { separatorColor: p.line, separatorHoverColor: withAlpha(p.accent, 0.25), enableResize: true },
      },
      grid: {
        vertLines: { color: withAlpha(p.line, look.gridAlpha), visible: look.grid === "full" },
        horzLines: { color: withAlpha(p.line, look.gridAlpha), visible: look.grid !== "none" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: withAlpha(p.fgSubtle, look.crosshair === LineStyle.Solid ? 0.45 : 1), width: 1, style: look.crosshair, labelBackgroundColor: p.raised },
        horzLine: { color: withAlpha(p.fgSubtle, look.crosshair === LineStyle.Solid ? 0.45 : 1), width: 1, style: look.crosshair, labelBackgroundColor: p.raised },
      },
      rightPriceScale: { borderColor: p.line, borderVisible: look.priceScaleBorder, scaleMargins: { top: 0.08, bottom: 0.2 } },
      timeScale: { borderColor: p.line, borderVisible: look.priceScaleBorder, rightOffset: 6, barSpacing: look.barSpacing, minBarSpacing: 2, timeVisible: true, secondsVisible: false,
        tickMarkFormatter: (t: Time, type: TickMarkType) => {
        if (typeof t !== "number") return String(t);
        const d = new Date(t * 1000);
        if (type === TickMarkType.Year) return fYear.format(d);
        if (type === TickMarkType.Month) return fMonth.format(d);
        if (type === TickMarkType.DayOfMonth) return fDay.format(d);
        return fTime.format(d);
      },
      },
      localization: {
        locale: "it-IT",
        priceFormatter: (v: number) => priceFmt.format(v),
        timeFormatter: (t: Time) => (typeof t === "number" ? (cbRef.current.timeframe === "1d" ? fFullDay : fFull).format(new Date(t * 1000)) : String(t)),
      },
      handleScale: { axisPressedMouseMove: { time: true, price: true } },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: p.up,
      downColor: p.down,
      borderUpColor: p.up,
      borderDownColor: p.down,
      wickUpColor: p.up,
      wickDownColor: p.down,
      priceLineColor: p.fgSubtle,
      priceLineStyle: LineStyle.Dotted,
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceScaleId: "vol",
      priceFormat: { type: "volume" },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, visible: false });

    const manager = new DrawingManager(chart, candles, { magnet: "weak", keyboard: true, touchHitTolerance: 16, interactive: cbRef.current.interactive });
    manager.on("add", (d) => {
      if (applying.current) return;
      // A drawing Luca just placed: sign it with his colour, then hand it to the Runtime.
      const color = cssColor("var(--author-luca)");
      applying.current = true;
      manager.update({ ...d, style: { ...d.style, color, textColor: color, width: 2 } } as Drawing);
      applying.current = false;
      cbRef.current.onCreate({ id: d.id, kind: d.kind, points: d.points.map((pt) => ({ time: Number(pt.time), price: pt.price })) });
    });
    manager.on("update", (d) => {
      if (applying.current) return;
      pendingUpdates.current.set(d.id, d);
    });
    manager.on("gestureEnd", () => {
      const list = [...pendingUpdates.current.values()];
      pendingUpdates.current.clear();
      for (const d of list) cbRef.current.onUpdate({ id: d.id, kind: d.kind, points: d.points.map((pt) => ({ time: Number(pt.time), price: pt.price })) });
    });
    manager.on("remove", (d) => {
      if (applying.current) return;
      cbRef.current.onRemove(d.id);
    });
    manager.on("tool", (kind) => cbRef.current.onToolChange(kind));

    const onMove = (param: MouseEventParams) => {
      if (param.time === undefined || !param.point) {
        setHover(null);
        return;
      }
      setHover(Number(param.time));
    };
    chart.subscribeCrosshairMove(onMove);

    chartRef.current = chart;
    candlesRef.current = candles;
    volumeRef.current = volume;
    managerRef.current = manager;
    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      manager.destroy();
      chart.remove();
      chartRef.current = null;
      candlesRef.current = null;
      volumeRef.current = null;
      managerRef.current = null;
      indicatorSeries.current.clear();
      priceLines.current = [];
      loadedKey.current = null;
    };
  }, []);

  // ---- bars ----------------------------------------------------------------------------------
  useEffect(() => {
    const chart = chartRef.current;
    const candles = candlesRef.current;
    const volume = volumeRef.current;
    const p = paletteRef.current;
    if (!chart || !candles || !volume || !p) return;
    const key = `${symbol}|${timeframe}`;
    const range: LogicalRange | null = loadedKey.current === key ? chart.timeScale().getVisibleLogicalRange() : null;
    candles.setData(bars.map((b) => ({ time: b.time as UTCTimestamp, open: b.open, high: b.high, low: b.low, close: b.close })));
    volume.setData(
      bars.map((b) => ({ time: b.time as UTCTimestamp, value: b.volume, color: withAlpha(b.close >= b.open ? p.up : p.down, look.volumeAlpha) })),
    );
    if (range) chart.timeScale().setVisibleLogicalRange(range);
    else if (bars.length) {
      const visible = intraday ? 180 : 140;
      chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, bars.length - visible), to: bars.length + 4 });
      loadedKey.current = key;
    }
    chart.timeScale().applyOptions({ timeVisible: intraday });
  }, [bars, symbol, timeframe, intraday]);

  // ---- indicators ----------------------------------------------------------------------------
  useEffect(() => {
    const chart = chartRef.current;
    const p = paletteRef.current;
    if (!chart || !p) return;
    for (const s of indicatorSeries.current.values()) chart.removeSeries(s);
    indicatorSeries.current.clear();
    if (!indicators) {
      paneIdsRef.current = [];
      setPaneTops([]);
      return;
    }
    const times = indicators.series;
    const line = (name: string) =>
      (indicators.indicators[name] ?? []).map((v, i) => (v === null || v === undefined ? { time: times[i] as UTCTimestamp } : { time: times[i] as UTCTimestamp, value: v }));

    let pane = 1;
    const tops: string[] = [];
    for (const spec of INDICATORS) {
      if (!enabled.includes(spec.id)) continue;
      if (spec.placement === "overlay") {
        const s = chart.addSeries(LineSeries, { color: INDICATOR_COLORS[spec.id], lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerRadius: 3 }, 0);
        s.setData(line(spec.request));
        indicatorSeries.current.set(spec.id, s);
        continue;
      }
      const idx = pane++;
      tops.push(spec.id);
      if (spec.id === "macd") {
        const hist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, idx);
        hist.setData(
          (indicators.indicators.macd_hist ?? []).map((v, i) =>
            v === null ? { time: times[i] as UTCTimestamp } : { time: times[i] as UTCTimestamp, value: v, color: withAlpha(v >= 0 ? p.up : p.down, 0.55) },
          ),
        );
        const l = chart.addSeries(LineSeries, { color: INDICATOR_COLORS.macd_line, lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, idx);
        l.setData(line("macd_line"));
        const sg = chart.addSeries(LineSeries, { color: INDICATOR_COLORS.macd_signal, lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, idx);
        sg.setData(line("macd_signal"));
        indicatorSeries.current.set("macd_hist", hist);
        indicatorSeries.current.set("macd_line", l);
        indicatorSeries.current.set("macd_signal", sg);
      } else {
        const s = chart.addSeries(LineSeries, { color: INDICATOR_COLORS[spec.id], lineWidth: 1, priceLineVisible: false, lastValueVisible: true }, idx);
        s.setData(line(spec.request));
        if (spec.id === "rsi14") {
          if (look.rsiGuides) for (const level of [70, 30]) s.createPriceLine({ price: level, color: withAlpha(p.fgSubtle, 0.3), lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "" });
          s.priceScale().applyOptions({ autoScale: false, scaleMargins: { top: 0.1, bottom: 0.1 } });
          s.applyOptions({ autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) });
        }
        indicatorSeries.current.set(spec.id, s);
      }
    }
    const panes = chart.panes();
    panes[0]?.setStretchFactor(3);
    for (let i = 1; i < panes.length; i++) panes[i].setStretchFactor(panes.length > 3 ? 0.8 : 1);
    // pane label positions, after layout (and again whenever the tile is resized)
    paneIdsRef.current = tops;
    requestAnimationFrame(measurePanes);
  }, [indicators, enabled]);

  // ---- drawings ------------------------------------------------------------------------------
  useEffect(() => {
    const manager = managerRef.current;
    if (!manager) return;
    applying.current = true;
    try {
      const wanted = new Map(drawings.map((d) => [d.id, d]));
      for (const existing of manager.drawings()) if (!wanted.has(existing.id)) manager.remove(existing.id);
      for (const d of drawings) {
        if (d.points.length !== pointCount(d.kind) && pointCount(d.kind) !== 2) continue;
        const a = resolveAuthor(d.author);
        const color = cssColor(a.color);
        const mine = a.kind === "human";
        const hl = highlightAuthor !== null && highlightAuthor === a.id;
        const dim = highlightAuthor !== null && highlightAuthor !== a.id;
        const label = look.fullLabels ? `${a.initials}${d.text ? ` · ${d.text}` : ""}` : a.initials;
        const style = {
          ...(manager.get(d.id)?.style ?? {}),
          ...(d.style ?? {}),
          color: dim ? withAlpha(color, 0.35) : color,
          textColor: dim ? withAlpha(color, 0.45) : color,
          width: hl ? look.drawingWidth + 1 : look.drawingWidth,
          lineStyle: !look.dashedLevels || mine ? "solid" : d.kind === "horizontal-line" ? "dashed" : "solid",
          text: label,
          fontSize: 11,
          horzLabelsAlign: d.kind === "horizontal-line" ? "left" : undefined,
          vertLabelsAlign: "top",
          ...(d.kind === "rectangle" ? { fillColor: withAlpha(color, dim ? 0.04 : 0.1), backgroundColor: withAlpha(color, dim ? 0.04 : 0.1), fillBackground: true } : {}),
        };
        const drawing = {
          id: d.id,
          kind: d.kind,
          points: d.points.map((pt) => ({ time: pt.time as UTCTimestamp, price: pt.price })),
          style,
          name: label,
          locked: !mine || !interactive,
          hidden: hiddenAuthors.includes(a.id),
        } as unknown as Drawing;
        try {
          if (manager.get(d.id)) manager.update(drawing);
          else manager.add(drawing);
        } catch (err) {
          console.warn("Disegno non valido ignorato", d.id, err);
        }
      }
    } finally {
      applying.current = false;
    }
  }, [drawings, hiddenAuthors, highlightAuthor, interactive]);

  useEffect(() => {
    managerRef.current?.setInteractive(interactive);
    if (!interactive) managerRef.current?.setTool(null);
  }, [interactive]);

  useEffect(() => {
    const m = managerRef.current;
    if (!m) return;
    if (m.tool() !== tool) m.setTool(tool);
  }, [tool]);

  useEffect(() => {
    if (!focusDrawing) return;
    const m = managerRef.current;
    const chart = chartRef.current;
    const d = drawings.find((x) => x.id === focusDrawing.id);
    if (!m || !chart || !d) return;
    m.select([d.id]);
    const t = d.points[0].time as UTCTimestamp;
    const idx = bars.findIndex((b) => b.time >= t);
    if (idx >= 0) {
      const r = chart.timeScale().getVisibleLogicalRange();
      const width = r ? r.to - r.from : 160;
      if (!r || idx < r.from || idx > r.to) chart.timeScale().setVisibleLogicalRange({ from: idx - width * 0.3, to: idx + width * 0.7 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusDrawing]);

  // ---- trade and order levels ----------------------------------------------------------------
  useEffect(() => {
    const candles = candlesRef.current;
    const p = paletteRef.current;
    if (!candles || !p) return;
    for (const pl of priceLines.current) candles.removePriceLine(pl);
    priceLines.current = marks.map((m) => {
      const color = m.tone === "tp" ? p.up : m.tone === "sl" ? p.down : m.tone === "trail" ? p.warn : m.tone === "pending" ? withAlpha(p.accent, 0.8) : p.accent;
      return candles.createPriceLine({
        price: m.price,
        color: look.markAlpha < 1 ? withAlpha(color, look.markAlpha) : color,
        lineWidth: 1,
        lineStyle: look.markStyle === LineStyle.Solid ? (m.tone === "pending" ? LineStyle.Dotted : LineStyle.Solid) : m.tone === "pending" ? LineStyle.SparseDotted : LineStyle.Dashed,
        axisLabelVisible: true,
        title: m.title,
        axisLabelColor: color,
        axisLabelTextColor: p.ground,
      });
    });
  }, [marks, bars]);

  // ---- legend ----------------------------------------------------------------------------------
  const legend = useMemo(() => {
    if (!bars.length) return null;
    let i = hover === null ? bars.length - 1 : bars.findIndex((b) => b.time === hover);
    if (i < 0) i = bars.length - 1;
    const b = bars[i];
    const prev = bars[i - 1];
    const change = prev ? b.close - prev.close : null;
    const pct = prev ? (change! / prev.close) * 100 : null;
    const ind: { id: string; label: string; value: number | null | undefined; color: string }[] = [];
    if (indicators) {
      const j = indicators.series.indexOf(b.time);
      for (const spec of INDICATORS) {
        if (!enabled.includes(spec.id) || spec.placement !== "overlay") continue;
        ind.push({ id: spec.id, label: spec.label, value: j >= 0 ? indicators.indicators[spec.request]?.[j] : null, color: INDICATOR_COLORS[spec.id] });
      }
    }
    const paneValues: Record<string, string> = {};
    if (indicators) {
      const j = indicators.series.indexOf(b.time);
      const v = (n: string) => (j >= 0 ? indicators.indicators[n]?.[j] : null);
      paneValues.rsi14 = fmtPrice(v("rsi14"));
      paneValues.atr14 = fmtPrice(v("atr14"));
      paneValues.macd = `${fmtPrice(v("macd_line"))} ${fmtPrice(v("macd_signal"))} ${fmtSigned(v("macd_hist"))}`;
    }
    return { b, change, pct, ind, paneValues };
  }, [bars, hover, indicators, enabled]);

  const hint = toolHintFor(tool);

  return (
    <div className={cn("relative min-h-0 min-w-0", props.className)}>
      <div ref={hostRef} className="absolute inset-0" />
      {legend && (
        <div className="pointer-events-none absolute left-4 top-1 z-10 flex max-w-[calc(100%-90px)] flex-col gap-1 text-[11px] leading-4">
          <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
            <span className="text-fg-faint">ET</span>
            <span className="num text-fg-subtle">
              A <span className={legend.b.close >= legend.b.open ? "text-up" : "text-down"}>{fmtPrice(legend.b.open)}</span>
            </span>
            <span className="num text-fg-subtle">
              Max <span className={legend.b.close >= legend.b.open ? "text-up" : "text-down"}>{fmtPrice(legend.b.high)}</span>
            </span>
            <span className="num text-fg-subtle">
              Min <span className={legend.b.close >= legend.b.open ? "text-up" : "text-down"}>{fmtPrice(legend.b.low)}</span>
            </span>
            <span className="num text-fg-subtle">
              C <span className={legend.b.close >= legend.b.open ? "text-up" : "text-down"}>{fmtPrice(legend.b.close)}</span>
            </span>
            {legend.change !== null && (
              <span className={cn("num", legend.change >= 0 ? "text-up" : "text-down")}>
                {fmtSigned(legend.change)} ({fmtSigned(legend.pct)}%)
              </span>
            )}
            <span className="num text-fg-subtle">
              Vol <span className="text-fg-muted">{fmtVolume(legend.b.volume)}</span>
            </span>
          </div>
          {legend.ind.length > 0 && (
            <div className="flex flex-wrap gap-x-3">
              {legend.ind.map((x) => (
                <span key={x.id} className="num text-fg-subtle">
                  {x.label} <span style={{ color: x.color }}>{fmtPrice(x.value)}</span>
                </span>
              ))}
            </div>
          )}
          {props.children && <div className="pointer-events-auto mt-0.5">{props.children}</div>}
        </div>
      )}
      {legend &&
        paneTops.map((pt) => {
          const spec = INDICATORS.find((s) => s.id === pt.id);
          if (!spec) return null;
          return (
            <div key={pt.id} className="pointer-events-none absolute left-2.5 z-10 text-[11px] leading-4" style={{ top: pt.top }}>
              <span className="text-fg-subtle">{spec.label}</span>{" "}
              <span className="num" style={{ color: INDICATOR_COLORS[pt.id === "macd" ? "macd_line" : pt.id] }}>
                {legend.paneValues[pt.id]}
              </span>
            </div>
          );
        })}
      {hint && (
        <div className="pointer-events-none absolute bottom-9 left-1/2 z-10 -translate-x-1/2 rounded-control border border-line-strong bg-raised/95 px-2.5 py-1 text-xs text-fg-muted shadow-[0_8px_24px_-8px_rgb(0_0_0/0.6)]">
          {hint}
        </div>
      )}
    </div>
  );
}
