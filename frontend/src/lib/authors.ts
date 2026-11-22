/**
 * Every mark in the cockpit shows who made it. The Runtime records the actor of each write:
 * human channels (cockpit, cli, telegram) are Luca; agent names are the office agents.
 */
export type AuthorKind = "human" | "agent" | "system";

export type Author = {
  id: string;
  kind: AuthorKind;
  name: string;
  short: string;
  initials: string;
  /** CSS colour token. */
  color: string;
  channel?: string;
  /** Ticker agents (`ticker:<SYM>`): the symbol they own; the avatar shows it instead of a monogram. */
  ticker?: string;
};

/** A ticker agent's identity is `ticker:<SYM>` (ADR 0004, .scratch/ticker-agents/brief.md). */
export const tickerAgentId = (symbol: string) => `ticker:${symbol.toUpperCase()}`;

export function tickerOf(actor: string | null | undefined): string | null {
  const m = /^ticker:(.+)$/i.exec((actor ?? "").trim());
  return m ? m[1].toUpperCase() : null;
}

const HUMAN_CHANNELS: Record<string, string> = {
  cockpit: "cockpit",
  user: "cockpit",
  luca: "cockpit",
  cli: "CLI",
  telegram: "Telegram",
};

export const AGENTS: Record<string, Omit<Author, "id" | "kind">> = {
  portfolio_manager: { name: "Portfolio Manager", short: "PM", initials: "PM", color: "var(--author-pm)" },
  technical_analyst: { name: "Technical Analyst", short: "Tecnico", initials: "TA", color: "var(--author-technical)" },
  market_analyst: { name: "Market Analyst", short: "Mercato", initials: "MA", color: "var(--author-market)" },
  sentiment_analyst: { name: "Sentiment Analyst", short: "Sentiment", initials: "SA", color: "var(--author-sentiment)" },
  fundamental_analyst: { name: "Fundamental Analyst", short: "Fondamentali", initials: "FA", color: "var(--author-fundamental)" },
  risk_analyst: { name: "Risk Analyst", short: "Rischio", initials: "RA", color: "var(--author-risk)" },
  subagent: { name: "Subagente", short: "Subagente", initials: "SB", color: "var(--author-system)" },
};

export const AGENT_IDS = Object.keys(AGENTS).filter((a) => a !== "subagent");

export const LUCA: Author = { id: "luca", kind: "human", name: "Luca", short: "Luca", initials: "LM", color: "var(--author-luca)", channel: "cockpit" };

export function author(actor: string | null | undefined): Author {
  const sym = tickerOf(actor);
  if (sym) {
    return { id: tickerAgentId(sym), kind: "agent", name: `Agente ${sym}`, short: sym, initials: sym.slice(0, 2), color: "var(--author-ticker)", ticker: sym };
  }
  const id = (actor ?? "").trim().toLowerCase();
  if (id in HUMAN_CHANNELS) return { ...LUCA, channel: HUMAN_CHANNELS[id] };
  const agent = AGENTS[id];
  if (agent) return { id, kind: "agent", ...agent };
  const label = id ? id.replace(/[-_]/g, " ") : "sconosciuto";
  return {
    id: id || "unknown",
    kind: "system",
    name: label === "dev seed" ? "Seed di sviluppo" : label.charAt(0).toUpperCase() + label.slice(1),
    short: label,
    initials: "SY",
    color: "var(--author-system)",
  };
}

const resolved = new Map<string, string>();

/** Resolved colour for canvas drawing (the chart cannot read CSS variables). */
export function cssColor(token: string): string {
  const m = token.match(/var\((--[^)]+)\)/);
  if (!m || typeof document === "undefined") return token;
  const hit = resolved.get(m[1]);
  if (hit) return hit;
  const probe = document.createElement("span");
  probe.style.color = `var(${m[1]})`;
  document.body.appendChild(probe);
  const value = toRgb(getComputedStyle(probe).color);
  document.body.removeChild(probe);
  resolved.set(m[1], value);
  return value || token;
}

let pixel: CanvasRenderingContext2D | null = null;

/** Canvas libraries (lightweight-charts) only parse rgb/hex: rasterise any CSS colour to rgb(a). */
export function toRgb(color: string): string {
  if (!color || color.startsWith("rgb") || color.startsWith("#")) return color;
  pixel ??= document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  if (!pixel) return color;
  pixel.clearRect(0, 0, 1, 1);
  pixel.fillStyle = color;
  pixel.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = pixel.getImageData(0, 0, 1, 1).data;
  return a === 255 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${+(a / 255).toFixed(3)})`;
}

/** Same colour with alpha, for canvas fills. Works with rgb()/oklch() strings from getComputedStyle. */
export function withAlpha(color: string, alpha: number): string {
  if (color.startsWith("rgb(")) return color.replace("rgb(", "rgba(").replace(")", `, ${alpha})`);
  if (color.startsWith("rgba(")) return color.replace(/,\s*[\d.]+\)$/, `, ${alpha})`);
  return color;
}
