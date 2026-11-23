import { toNum } from "@/lib/format";
import type { DecideAction } from "./types";

/** Dossier lifecycle as Luca reads it. Unknown values from the Runtime are shown verbatim. */
export const DOSSIER_STATUS: Record<string, string> = {
  idle: "Inattiva",
  analyzing: "In analisi",
  proposed: "Proposta al PM",
  approved: "Approvata",
  declined: "Respinta",
  monitoring: "In monitoraggio",
};

export const PROPOSAL_STATUS: Record<string, string> = {
  pending: "In attesa del PM",
  accepted: "Accettata",
  deferred: "Rimandata",
  rejected: "Rifiutata",
  asked: "Domande al ticker",
};

export const DECIDE_LABEL: Record<DecideAction, string> = { accept: "Accetta", defer: "Rimanda", reject: "Rifiuta", ask: "Chiedi" };

export const ACTION_LABEL: Record<string, string> = { ...DECIDE_LABEL, accept: "Accettata", defer: "Rimandata", reject: "Rifiutata", ask: "Domande", submit: "Proposta", approved: "Approvata", rejected: "Rifiutata" };

const DIRECTION: Record<string, { label: string; tone: "up" | "down" | "flat" }> = {
  long: { label: "Long", tone: "up" },
  buy: { label: "Long", tone: "up" },
  bullish: { label: "Rialzista", tone: "up" },
  short: { label: "Short", tone: "down" },
  sell: { label: "Short", tone: "down" },
  bearish: { label: "Ribassista", tone: "down" },
  hold: { label: "Neutrale", tone: "flat" },
  neutral: { label: "Neutrale", tone: "flat" },
  flat: { label: "Neutrale", tone: "flat" },
};

export function direction(d: string | null | undefined): { label: string; tone: "up" | "down" | "flat" } | null {
  if (!d) return null;
  return DIRECTION[d.toLowerCase()] ?? { label: d, tone: "flat" };
}

/** Risk Gate verdicts the Runtime may send: pass reads up, anything blocking reads down. */
export function verdictTone(v: string | null | undefined): "ok" | "block" | "neutral" {
  const s = (v ?? "").toLowerCase();
  if (["pass", "passed", "ok", "approved", "accepted", "allow", "allowed"].includes(s)) return "ok";
  if (["fail", "failed", "rejected", "blocked", "block", "deny", "denied", "veto"].includes(s)) return "block";
  return "neutral";
}

const frac0 = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 });
const frac1 = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const dec2 = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

/** 0.0425 → "4,3%"; whole numbers drop the decimal. Fractions per contract. */
export function fmtFraction(v: unknown, opts: { decimals?: 0 | 1 } = {}): string {
  const n = toNum(v);
  if (n === null) return "—";
  const pct = n * 100;
  return `${(opts.decimals === 0 || Number.isInteger(pct) ? frac0 : frac1).format(pct)}%`;
}

/** Conviction and confidence, 0..1, as two decimals ("0,72"). */
export const fmtScore = (v: unknown) => {
  const n = toNum(v);
  return n === null ? "—" : dec2.format(n);
};

export const fmtRR = (v: unknown) => {
  const n = toNum(v);
  return n === null ? "—" : dec2.format(n);
};

const dayFmt = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", year: "numeric" });
const dayShort = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short" });

/** A calendar date ("2026-11-25" or ISO): same year drops the year. */
export function fmtDate(v: string | null | undefined, now = Date.now()): string {
  if (!v) return "—";
  const ms = Date.parse(v.length === 10 ? `${v}T12:00:00Z` : v);
  if (!Number.isFinite(ms)) return v;
  const d = new Date(ms);
  return d.getFullYear() === new Date(now).getFullYear() ? dayShort.format(d) : dayFmt.format(d);
}

/** Days from today to a date: negative when past. */
export function daysUntil(v: string | null | undefined, now = Date.now()): number | null {
  if (!v) return null;
  const ms = Date.parse(v.length === 10 ? `${v}T12:00:00Z` : v);
  if (!Number.isFinite(ms)) return null;
  const a = new Date(now);
  a.setHours(0, 0, 0, 0);
  const b = new Date(ms);
  b.setHours(0, 0, 0, 0);
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

const SECTION: Record<string, string> = {
  technical: "Tecnica",
  market: "Mercato",
  sentiment: "Sentiment",
  fundamental: "Fondamentali",
  fundamentals: "Fondamentali",
  risk: "Rischio",
  thesis: "Tesi",
  proposal: "Proposta",
  notes: "Note",
  decisions: "Decisioni",
  lessons: "Lezioni",
  identity: "Identità",
  portfolio: "Portafoglio",
  desks: "Analisi",
};

export const sectionLabel = (s: string) => SECTION[s.toLowerCase()] ?? s.replace(/[_-]/g, " ").replace(/^./, (c) => c.toUpperCase());
