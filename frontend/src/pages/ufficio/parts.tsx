import { Info } from "lucide-react";
import type { CSSProperties, KeyboardEvent, ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { AgentStatus, Sourced, UsageTotals } from "@/features/office/types";
import { author } from "@/lib/authors";
import { fmtMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

/** What each seat in the office does. Static presentation; the Runtime's `role` wins when it sends one. */
export const ROLE: Record<string, string> = {
  portfolio_manager: "Decide e firma gli ordini",
  technical_analyst: "Prezzo, livelli e indicatori",
  market_analyst: "Flussi e contesto di mercato",
  sentiment_analyst: "Notizie e sentiment",
  fundamental_analyst: "Bilanci e valutazioni",
  risk_analyst: "Rischio ed esposizione",
  subagent: "Ricerche delegate",
};

export const STATUS_LABEL: Record<AgentStatus, string> = { working: "Al lavoro", waiting: "In attesa", idle: "Inattivo" };

const int0 = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0, useGrouping: "always" });
const dec1 = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 1, minimumFractionDigits: 0 });
const dec2 = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

/** "840", "182 K", "1,24 M" */
export function fmtTokens(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  if (n >= 1e6) return `${dec2.format(n / 1e6)} M`;
  if (n >= 1e4) return `${int0.format(n / 1e3)} K`;
  if (n >= 1e3) return `${dec1.format(n / 1e3)} K`;
  return int0.format(n);
}

export function fmtCost(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return fmtMoney(n, { decimals: n !== 0 && Math.abs(n) < 0.1 ? 3 : 2 });
}

export const totalTokens = (u: UsageTotals | null | undefined) => (u ? u.tokens_in + u.tokens_out : null);

/**
 * The agent's state as a dot and a word. Working is drawn in the agent's own colour and breathes while live;
 * waiting is warn; idle is a hollow ring. Unknown says so instead of guessing.
 */
export function StatusMark({ agent, status, compact = false, className }: { agent: string; status: AgentStatus | null; compact?: boolean; className?: string }) {
  const color = author(agent).color;
  const label = status ? STATUS_LABEL[status] : "Stato non esposto";
  const dot = (
    <span
      aria-hidden
      className={cn(
        "relative inline-block size-2 shrink-0 rounded-full",
        status === "waiting" && "bg-warn",
        status === "idle" && "shadow-[inset_0_0_0_1.5px_var(--fg-subtle)]",
        status === null && "shadow-[inset_0_0_0_1.5px_var(--line-strong)]",
        status === "working" && "agent-working",
      )}
      style={status === "working" ? ({ backgroundColor: color, ["--agent" as string]: color } as CSSProperties) : undefined}
    />
  );
  if (compact) {
    return (
      <Tooltip>
        <TooltipTrigger
          render={
            <span className={cn("inline-grid size-4 place-items-center", className)} role="img" aria-label={label}>
              {dot}
            </span>
          }
        />
        <TooltipContent>{label}</TooltipContent>
      </Tooltip>
    );
  }
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-xs", status === null ? "text-fg-subtle" : status === "idle" ? "text-fg-muted" : "text-fg", className)}>
      {dot}
      {label}
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

export function TickerTag({ ticker, className }: { ticker: string; className?: string }) {
  return <span className={cn("num inline-flex h-5 items-center rounded-tag bg-hover px-1.5 text-2xs font-semibold tracking-[0.01em] text-fg", className)}>{ticker}</span>;
}

/** Label + value pair used in seats and usage popovers. */
export function Meter({ label, value, hint, className }: { label: string; value: ReactNode; hint?: string; className?: string }) {
  const body = (
    <div className={cn("min-w-0", className)}>
      <dt className="truncate text-2xs text-fg-subtle">{label}</dt>
      <dd className="num mt-0.5 truncate text-xs text-fg">{value}</dd>
    </div>
  );
  if (!hint) return body;
  return (
    <Tooltip>
      <TooltipTrigger render={body} />
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  );
}

/** Arrow keys move the choice inside a custom radiogroup, as ARIA expects; Tab leaves the group. */
export function onRadioKeys(e: KeyboardEvent<HTMLElement>) {
  const keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"];
  if (!keys.includes(e.key)) return;
  const radios = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]:not(:disabled)'));
  const i = radios.indexOf(document.activeElement as HTMLButtonElement);
  if (i < 0 || !radios.length) return;
  e.preventDefault();
  const next = e.key === "Home" ? 0 : e.key === "End" ? radios.length - 1 : (i + (e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1) + radios.length) % radios.length;
  radios[next].focus();
  radios[next].click();
}
