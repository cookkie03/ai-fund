import { BookOpen, Forward, Info, Quote, WifiOff } from "lucide-react";
import type { ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { NewsUsage } from "@/features/news/types";
import { RuntimeError } from "@/lib/runtime/client";
import { cn } from "@/lib/utils";

/** Ticker as a 4 px tag; holdings read brighter than the rest. */
export function TickerTag({ symbol, strong, className }: { symbol: string; strong?: boolean; className?: string }) {
  return (
    <span className={cn("num inline-flex h-4 items-center rounded-tag px-1 text-[10px] font-semibold tracking-[0.02em]", strong ? "bg-selected text-fg" : "bg-hover text-fg-muted", className)}>
      {symbol}
    </span>
  );
}

const MARKS = [
  { key: "reads", icon: BookOpen, one: "lettura", many: "letture", tone: "text-fg-muted" },
  { key: "citations", icon: Quote, one: "citazione", many: "citazioni", tone: "text-fg" },
  { key: "forwards", icon: Forward, one: "inoltro di Luca", many: "inoltri di Luca", tone: "text-[var(--author-luca)]" },
] as const;

/** How the office used an item: reads, citations, Luca's forwards. Nothing drawn when nobody used it. */
export function UsageMarks({ usage, className }: { usage: NewsUsage; className?: string }) {
  const marks = MARKS.filter((m) => usage[m.key] > 0);
  if (!marks.length) return null;
  const label = marks.map((m) => `${usage[m.key]} ${usage[m.key] === 1 ? m.one : m.many}`).join(", ");
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span data-part="usage" aria-label={`Uso da parte dell'ufficio: ${label}`} className={cn("inline-flex shrink-0 items-center gap-2", className)}>
          {marks.map(({ key, icon: Icon, tone }) => (
            <span key={key} className={cn("num inline-flex items-center gap-0.5 text-[11px]", tone)}>
              <Icon className="size-3" strokeWidth={2} aria-hidden />
              {usage[key]}
            </span>
          ))}
        </span>
      </TooltipTrigger>
      <TooltipContent side="left">{label.charAt(0).toUpperCase() + label.slice(1)}</TooltipContent>
    </Tooltip>
  );
}

/** A quiet in-tile notice: unavailable endpoint, empty filter, unreachable Runtime. */
export function Notice({ icon, title, detail, children, className }: { icon?: ReactNode; title: string; detail?: ReactNode; children?: ReactNode; className?: string }) {
  return (
    <div role="status" className={cn("flex flex-col items-start gap-1.5 px-5 py-6 text-left", className)}>
      <span className="text-fg-subtle [&_svg]:size-4">{icon ?? <Info />}</span>
      <p className="text-[13px] font-medium text-fg">{title}</p>
      {detail && <p className="max-w-[52ch] text-xs leading-[1.1rem] text-fg-muted">{detail}</p>}
      {children && <div className="mt-1.5 flex flex-wrap gap-1.5">{children}</div>}
    </div>
  );
}

/** An error from a read, phrased for Luca: unreachable Runtime or the Runtime's own detail. */
export function ReadError({ error, what }: { error: unknown; what: string }) {
  const unreachable = error instanceof RuntimeError && error.unreachable;
  return (
    <Notice
      icon={<WifiOff />}
      title={unreachable ? "Runtime irraggiungibile" : `Non riesco a leggere ${what}`}
      detail={unreachable ? `${what.charAt(0).toUpperCase() + what.slice(1)} torneranno appena il Runtime risponde: riprovo da solo.` : error instanceof Error ? error.message : String(error)}
    />
  );
}
