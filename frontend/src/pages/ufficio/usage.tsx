import { ChevronDown, Coins } from "lucide-react";
import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { PERIOD_LABEL, useUsage, type UsagePeriod } from "@/features/office/hooks";
import { AGENTS } from "@/lib/authors";
import { cn } from "@/lib/utils";
import { fmtCost, fmtTokens, Meter, totalTokens, onRadioKeys } from "./parts";

const PERIODS: UsagePeriod[] = ["today", "7d", "30d"];

/** Cost and tokens of one agent: today in the trigger, any period in the popover. */
export function UsageButton({ agent, className }: { agent: string; className?: string }) {
  const [period, setPeriod] = useState<UsagePeriod>("today");
  const today = useUsage(agent, "today");
  const chosen = useUsage(agent, period);
  const todayRow = today.data?.source === "runtime" ? today.data.data.find((r) => r.agent === agent) ?? today.data.data[0] : null;
  const row = chosen.data?.source === "runtime" ? chosen.data.data.find((r) => r.agent === agent) ?? chosen.data.data[0] ?? null : null;
  const unavailable = today.data?.source === "unavailable";

  return (
    <Popover>
      <PopoverTrigger
        className={cn("inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-control px-2 text-xs transition-colors hover:bg-hover", className)}
        aria-label={`Costi e token di ${AGENTS[agent]?.name ?? agent}`}
      >
        <Coins className="size-3.5 text-fg-subtle" aria-hidden />
        {today.isPending ? (
          <span className="h-3 w-20 animate-pulse rounded-tag bg-hover" />
        ) : unavailable || today.isError ? (
          <span className="text-fg-subtle">Costi n/d</span>
        ) : (
          <span className="num text-fg-muted">
            <span className="text-fg">{fmtCost(todayRow?.cost ?? 0)}</span> · {fmtTokens(totalTokens(todayRow) ?? 0)} token
          </span>
        )}
        <ChevronDown className="size-3 text-fg-subtle" aria-hidden />
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-0">
        <div className="flex items-center gap-2 px-3.5 pb-2 pt-3">
          <h3 className="text-[13px] font-semibold text-fg">Uso di {AGENTS[agent]?.short ?? agent}</h3>
        </div>
        <div className="px-3.5 pb-2">
          <div role="radiogroup" aria-label="Periodo" className="seg w-full" onKeyDown={onRadioKeys}>
            {PERIODS.map((p) => (
              <button key={p} type="button" role="radio" aria-checked={period === p} tabIndex={period === p ? 0 : -1} onClick={() => setPeriod(p)} className="seg-item flex-1 justify-center">
                {PERIOD_LABEL[p]}
              </button>
            ))}
          </div>
        </div>
        {chosen.data?.source === "unavailable" || chosen.isError ? (
          <p className="px-3.5 pb-3.5 pt-1 text-xs leading-relaxed text-fg-muted">
            {chosen.isError ? `Lettura non riuscita: ${chosen.error.message}` : chosen.data?.source === "unavailable" ? chosen.data.note : null} Arrivano con l'endpoint <span className="text-fg">usage</span> del Runtime.
          </p>
        ) : (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-3.5 pb-3.5 pt-1.5">
            <Meter label="Costo" value={chosen.isPending ? "…" : fmtCost(row?.cost ?? 0)} />
            <Meter label="Chiamate al modello" value={chosen.isPending ? "…" : fmtTokens(row?.calls ?? 0)} />
            <Meter label="Token in ingresso" value={chosen.isPending ? "…" : fmtTokens(row?.tokens_in ?? 0)} />
            <Meter label="Token in uscita" value={chosen.isPending ? "…" : fmtTokens(row?.tokens_out ?? 0)} />
          </dl>
        )}
      </PopoverContent>
    </Popover>
  );
}
