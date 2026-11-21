import { LineStyle } from "lightweight-charts";

/**
 * Exploration only (phase 1 of the "Apple-like" refinement): `?variant=a|b|c` switches the whole
 * shell and Terminale to a candidate direction. No parameter keeps the shipped build untouched.
 */
export type Variant = "current" | "a" | "b" | "c";

export const VARIANTS: { id: Variant; label: string; hint: string }[] = [
  { id: "current", label: "Attuale", hint: "La build di oggi" },
  { id: "a", label: "A · Calma", hint: "Livelli leggeri, meno linee, densità con calma (Linear)" },
  { id: "b", label: "B · Legend", hint: "Moduli a tessere su fondo nero, prezzo protagonista (Robinhood Legend)" },
  { id: "c", label: "C · Borsa", hint: "Barra laterale e pannelli macOS, tipografia grande e respiro (Borsa, Finder)" },
];

const KEY = "cockpit.variant";

function read(): Variant {
  if (typeof window === "undefined") return "current";
  const q = new URLSearchParams(window.location.search).get("variant");
  const valid = (v: string | null): v is Variant => v === "a" || v === "b" || v === "c" || v === "current";
  if (valid(q)) {
    try {
      sessionStorage.setItem(KEY, q);
    } catch {
      /* private mode: the URL still carries it */
    }
    return q;
  }
  try {
    const s = sessionStorage.getItem(KEY);
    if (valid(s)) return s;
  } catch {
    /* ignore */
  }
  return "current";
}

export const variant: Variant = read();
export const exploring = variant !== "current";
/** The switcher shows once a variant link has been opened in this tab, "Attuale" included. */
export const showSwitcher = (() => {
  try {
    return new URLSearchParams(window.location.search).has("variant") || sessionStorage.getItem(KEY) !== null;
  } catch {
    return exploring;
  }
})();

if (typeof document !== "undefined" && exploring) document.documentElement.dataset.variant = variant;

export function switchVariant(v: Variant) {
  const url = new URL(window.location.href);
  url.searchParams.set("variant", v);
  window.location.assign(url.toString());
}

export type ChartLook = {
  grid: "full" | "horz" | "none";
  gridAlpha: number;
  crosshair: LineStyle;
  drawingWidth: number;
  /** Agents' horizontal levels dashed (current) or all drawings solid. */
  dashedLevels: boolean;
  /** Full "TA · text" labels on the chart, or the monogram only (text lives in the Disegni tab). */
  fullLabels: boolean;
  markStyle: LineStyle;
  markAlpha: number;
  volumeAlpha: number;
  rsiGuides: boolean;
  barSpacing: number;
  priceScaleBorder: boolean;
};

const LOOKS: Record<Variant, ChartLook> = {
  current: { grid: "full", gridAlpha: 0.45, crosshair: LineStyle.Dashed, drawingWidth: 2, dashedLevels: true, fullLabels: true, markStyle: LineStyle.Dashed, markAlpha: 1, volumeAlpha: 0.24, rsiGuides: true, barSpacing: 7, priceScaleBorder: true },
  a: { grid: "horz", gridAlpha: 0.22, crosshair: LineStyle.Solid, drawingWidth: 1.5, dashedLevels: false, fullLabels: false, markStyle: LineStyle.Solid, markAlpha: 0.55, volumeAlpha: 0.16, rsiGuides: true, barSpacing: 7, priceScaleBorder: false },
  b: { grid: "none", gridAlpha: 0, crosshair: LineStyle.Solid, drawingWidth: 1.5, dashedLevels: false, fullLabels: false, markStyle: LineStyle.Solid, markAlpha: 0.45, volumeAlpha: 0.12, rsiGuides: false, barSpacing: 8, priceScaleBorder: false },
  c: { grid: "horz", gridAlpha: 0.14, crosshair: LineStyle.Solid, drawingWidth: 1.5, dashedLevels: false, fullLabels: false, markStyle: LineStyle.Solid, markAlpha: 0.5, volumeAlpha: 0.14, rsiGuides: false, barSpacing: 8, priceScaleBorder: false },
};

export const chartLook: ChartLook = LOOKS[variant];
