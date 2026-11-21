/**
 * ChartState: the one source of truth shared by the UI and the Runtime. The chart libraries
 * (lightweight-charts, lightweight-charts-drawing) are only views of it and stay replaceable.
 *
 * Drawings are stored in the Runtime as annotations: `{ type, points: [{time, price}], text?, style? }`
 * where `type` is the drawing kind (TradingView names, e.g. "trend-line"). Agents read and write
 * the same shape.
 */
import type { DrawingKind } from "lightweight-charts-drawing";
import type { Annotation, RuntimeDrawing } from "@/lib/runtime/types";

export type IndicatorId = "ema20" | "sma50" | "rsi14" | "atr14" | "macd";

export type IndicatorSpec = {
  id: IndicatorId;
  label: string;
  /** Names requested from /v1/read/indicators. */
  request: string;
  /** Overlay on price, or own pane. */
  placement: "overlay" | "pane";
  description: string;
};

export const INDICATORS: IndicatorSpec[] = [
  { id: "ema20", label: "EMA 20", request: "ema20", placement: "overlay", description: "Media mobile esponenziale a 20 periodi" },
  { id: "sma50", label: "SMA 50", request: "sma50", placement: "overlay", description: "Media mobile semplice a 50 periodi" },
  { id: "rsi14", label: "RSI 14", request: "rsi14", placement: "pane", description: "Relative Strength Index, soglie 30 / 70" },
  { id: "macd", label: "MACD", request: "macd", placement: "pane", description: "MACD 12 / 26 / 9" },
  { id: "atr14", label: "ATR 14", request: "atr14", placement: "pane", description: "Average True Range, la volatilità che usano stop e target" },
];

export type ChartDrawing = {
  id: string;
  ticker: string;
  timeframe: string | null;
  author: string;
  status: "active" | "struck";
  struckBy: string | null;
  kind: DrawingKind;
  points: { time: number; price: number }[];
  text?: string;
  style?: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type ChartState = {
  symbol: string | null;
  /** null = the Runtime default (`[market].bar_timeframe`). */
  timeframe: string | null;
  indicators: IndicatorId[];
  drawings: ChartDrawing[];
  /** Author ids whose marks are hidden on the chart. */
  hiddenAuthors: string[];
};

export const DEFAULT_INDICATORS: IndicatorId[] = ["ema20", "sma50", "rsi14"];

const KIND_ALIASES: Record<string, DrawingKind> = {
  trendline: "trend-line",
  trend_line: "trend-line",
  line: "trend-line",
  hline: "horizontal-line",
  horizontal: "horizontal-line",
  horizontal_line: "horizontal-line",
  level: "horizontal-line",
  support: "horizontal-line",
  resistance: "horizontal-line",
  hray: "horizontal-ray",
  vline: "vertical-line",
  vertical: "vertical-line",
  rect: "rectangle",
  box: "rectangle",
  zone: "rectangle",
  fib: "fib-retracement",
  fibonacci: "fib-retracement",
};

/** Kinds the cockpit offers in its toolbar. Anything else an agent writes is still drawn. */
export const TOOLBAR_KINDS: DrawingKind[] = ["trend-line", "horizontal-line", "ray", "rectangle", "fib-retracement", "parallel-channel"];

export const KIND_LABEL: Partial<Record<DrawingKind, string>> = {
  "trend-line": "Linea di tendenza",
  "horizontal-line": "Linea orizzontale",
  "horizontal-ray": "Raggio orizzontale",
  "vertical-line": "Linea verticale",
  ray: "Raggio",
  rectangle: "Rettangolo",
  "fib-retracement": "Ritracciamento di Fibonacci",
  "parallel-channel": "Canale parallelo",
  "extended-line": "Linea estesa",
  "price-label": "Etichetta di prezzo",
  text: "Testo",
};

export function normalizeKind(type: string): DrawingKind {
  const t = type.trim().toLowerCase();
  return (KIND_ALIASES[t] ?? t) as DrawingKind;
}

/** Points each kind needs; the library rejects drawings with the wrong count. */
export function pointCount(kind: DrawingKind): number {
  if (["horizontal-line", "horizontal-ray", "vertical-line", "cross-line", "price-label", "arrow-mark-up", "arrow-mark-down", "flag-mark", "text", "note", "pin"].includes(kind)) return 1;
  if (["parallel-channel", "pitchfork", "triangle", "trend-based-fib-extension"].includes(kind)) return 3;
  return 2;
}

export function fromAnnotation(a: Annotation): ChartDrawing | null {
  const d = a.drawing;
  if (!d || typeof d.type !== "string" || !Array.isArray(d.points) || !d.points.length) return null;
  const kind = normalizeKind(d.type);
  return {
    id: a.id,
    ticker: a.ticker,
    timeframe: a.timeframe,
    author: a.author,
    status: a.status === "struck" ? "struck" : "active",
    struckBy: a.struck_by,
    kind,
    points: d.points.map((p) => ({ time: Number(p.time), price: Number(p.price) })),
    text: typeof d.text === "string" ? d.text : undefined,
    style: d.style && typeof d.style === "object" ? d.style : undefined,
    createdAt: a.created_at,
    updatedAt: a.updated_at,
  };
}

export function toRuntimeDrawing(d: Pick<ChartDrawing, "kind" | "points" | "text" | "style">): RuntimeDrawing {
  const out: RuntimeDrawing = { type: d.kind, points: d.points.map((p) => ({ time: Math.round(p.time), price: Math.round(p.price * 100) / 100 })) };
  if (d.text) out.text = d.text;
  if (d.style) out.style = d.style;
  return out;
}

export const TIMEFRAMES = [
  { id: "15m", label: "15m" },
  { id: "1h", label: "1H" },
  { id: "1d", label: "1G" },
] as const;

const STORAGE = "cockpit.chart";

/** View preferences persist per browser; drawings never do (they live in the Runtime). */
export function loadPrefs(): Pick<ChartState, "indicators" | "hiddenAuthors"> & { timeframe: string | null } {
  try {
    const raw = localStorage.getItem(STORAGE);
    if (raw) {
      const p = JSON.parse(raw);
      return {
        indicators: Array.isArray(p.indicators) ? p.indicators.filter((i: string) => INDICATORS.some((s) => s.id === i)) : DEFAULT_INDICATORS,
        hiddenAuthors: Array.isArray(p.hiddenAuthors) ? p.hiddenAuthors : [],
        timeframe: typeof p.timeframe === "string" ? p.timeframe : null,
      };
    }
  } catch {
    /* storage unavailable */
  }
  return { indicators: DEFAULT_INDICATORS, hiddenAuthors: [], timeframe: null };
}

export function savePrefs(p: { indicators: IndicatorId[]; hiddenAuthors: string[]; timeframe: string | null }) {
  try {
    localStorage.setItem(STORAGE, JSON.stringify(p));
  } catch {
    /* storage unavailable */
  }
}
