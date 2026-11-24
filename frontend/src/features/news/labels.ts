import { parseTs } from "@/lib/format";
import type { Importance, SourceStatus, UsageKind } from "./types";

export const PROVIDER_LABEL: Record<string, string> = { alpaca: "Alpaca", rss: "RSS", openbb: "OpenBB" };
export const providerLabel = (p: string) => PROVIDER_LABEL[p] ?? p;

export const SCOPE_LABEL = { all: "Tutte", portfolio: "Portafoglio", watchlist: "Watchlist" } as const;

export const USAGE_VERB: Record<UsageKind, string> = { read: "l'ha letta", cited: "l'ha citata", forwarded: "l'ha ricevuta da Luca" };

export const SOURCE_STATUS_LABEL: Record<SourceStatus, string> = { ok: "Attiva", error: "In errore", unavailable: "Non disponibile" };

export const IMPORTANCE_LABEL: Record<Importance, string> = { low: "Bassa", medium: "Media", high: "Alta" };
export const IMPORTANCE_LEVEL: Record<Importance, number> = { low: 1, medium: 2, high: 3 };

const dayFmt = new Intl.DateTimeFormat("it-IT", { weekday: "long", day: "numeric", month: "long" });
const timeFmt = new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" });
const fullFmt = new Intl.DateTimeFormat("it-IT", { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

/** "Oggi", "Ieri", "Domani" or "martedì 24 novembre". */
export function dayLabel(ts: string | null | undefined, now = Date.now()): string {
  const ms = parseTs(ts);
  if (ms === null) return "—";
  const d = new Date(ms);
  d.setHours(0, 0, 0, 0);
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((d.getTime() - today.getTime()) / 86_400_000);
  if (diff === 0) return "Oggi";
  if (diff === -1) return "Ieri";
  if (diff === 1) return "Domani";
  const s = dayFmt.format(d);
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const dayKey = (ts: string) => {
  const ms = parseTs(ts);
  return ms === null ? "" : new Date(ms).toDateString();
};

export const fmtClock = (ts: string | null | undefined) => {
  const ms = parseTs(ts);
  return ms === null ? "—" : timeFmt.format(new Date(ms));
};

export const fmtFull = (ts: string | null | undefined) => {
  const ms = parseTs(ts);
  return ms === null ? "—" : fullFmt.format(new Date(ms));
};

/** Host of a link, for "Apri su reuters.com". */
export function hostOf(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

/** Only http(s) links leave the cockpit. */
export const safeUrl = (url: string | null) => (url && /^https?:\/\//i.test(url) ? url : null);
