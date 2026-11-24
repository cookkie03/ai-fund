import { useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAllocation } from "@/features/portfolio/hooks";
import type { AllocationRow } from "@/features/portfolio/types";
import { cn } from "@/lib/utils";
import { onRadioKeys } from "@/pages/ufficio/parts";
import { Bones, fmtFrac, fmtMoney, LimitBar, SourceNote, statusFor, STATUS_WORD, StatusWord, TileTitle } from "./parts";

type View = "sector" | "position";

function Row({ label, row, scale, min = false, sub }: { label: string; row: AllocationRow; scale: number; min?: boolean; sub?: string }) {
  const status = statusFor(row.weight, row.limit, min);
  const tip = `${label}: ${fmtFrac(row.weight, { decimals: 1 })} · ${fmtMoney(row.value, { decimals: 0 })}${row.limit !== null ? ` · ${min ? "minimo" : "soglia"} ${fmtFrac(row.limit, { decimals: 0 })} · ${STATUS_WORD[status].toLowerCase()}` : ""}`;
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <li tabIndex={0} className="grid grid-cols-[5.5rem_1fr_3.25rem] items-center gap-3 rounded-item px-2.5 py-[7px] outline-none transition-colors duration-150 hover:bg-hover focus-visible:ring-2 focus-visible:ring-ring/60">
            <span className="min-w-0">
              <span className="block truncate text-xs font-medium text-fg">{label}</span>
              {sub && <span className="num block truncate text-2xs text-fg-subtle">{sub}</span>}
            </span>
            <LimitBar value={row.weight} limit={row.limit} scale={scale} status={status} min={min} label={tip} />
            <span className="text-right">
              <span className={cn("num block text-xs", status === "breach" ? "text-down" : status === "near" ? "text-warn" : "text-fg")}>{fmtFrac(row.weight, { decimals: 1 })}</span>
            </span>
          </li>
        }
      />
      <TooltipContent side="left">{tip}</TooltipContent>
    </Tooltip>
  );
}

/**
 * Allocation as horizontal bars, each with its Risk Gate limit as a tick (no pie). Sectors and positions share
 * one scale per view, wide enough to show the limit; cash closes the list against its minimum reserve.
 */
export function AllocationTile({ className }: { className?: string }) {
  const q = useAllocation();
  const [pick, setPick] = useState<View | null>(null);
  const data = q.data && q.data.source !== "unavailable" ? q.data.data : null;
  const hasSectors = (data?.by_sector.length ?? 0) > 0;
  const view: View = pick ?? (hasSectors ? "sector" : "position");
  const rows: (AllocationRow & { label: string; sub?: string })[] =
    view === "sector"
      ? (data?.by_sector ?? []).map((r) => ({ ...r, label: r.sector, sub: fmtMoney(r.value, { decimals: 0 }) }))
      : (data?.by_position ?? []).map((r) => ({ ...r, label: r.ticker, sub: fmtMoney(r.value, { decimals: 0 }) }));
  const limit = rows.find((r) => r.limit !== null)?.limit ?? null;
  const scale = Math.max(limit !== null ? limit * 1.2 : 0, ...rows.map((r) => r.weight * 1.08), 0.05);
  const flagged = rows.filter((r) => statusFor(r.weight, r.limit) !== "ok");
  const cash = data?.cash;

  return (
    <section aria-label="Allocazione" data-region="allocation" className={cn("flex min-w-0 flex-col rounded-tile bg-ground", className)}>
      <TileTitle
        meta={limit !== null ? <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-2.5 w-[2px] rounded-full bg-fg" />soglia {fmtFrac(limit, { decimals: 0 })}</span> : undefined}
        end={
          <div role="radiogroup" aria-label="Raggruppa per" className="seg" onKeyDown={onRadioKeys}>
            {(["sector", "position"] as const).map((v) => (
              <button key={v} type="button" role="radio" aria-checked={view === v} tabIndex={view === v ? 0 : -1} onClick={() => setPick(v)} className="seg-item">
                {v === "sector" ? "Settori" : "Posizioni"}
              </button>
            ))}
          </div>
        }
      >
        Allocazione
      </TileTitle>

      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {q.isPending ? (
          <Bones rows={5} className="px-2.5 pt-1" />
        ) : q.isError ? (
          <p className="px-2.5 py-4 text-xs text-down">Allocazione non disponibile: {q.error.message}</p>
        ) : view === "sector" && !hasSectors ? (
          <p className="px-2.5 py-4 text-xs leading-relaxed text-fg-muted">
            I settori arrivano con <span className="num text-fg">/v1/read/allocation</span>: il Runtime non li espone ancora. La vista Posizioni usa i pesi reali del broker.
          </p>
        ) : rows.length === 0 ? (
          <p className="px-2.5 py-4 text-xs text-fg-subtle">Nessuna posizione aperta: tutto il conto è in cassa.</p>
        ) : (
          <>
            {flagged.length > 0 && (
              <p className="flex flex-wrap items-center gap-1.5 px-2.5 pb-1.5 text-2xs text-fg-muted">
                <StatusWord status={flagged.some((r) => statusFor(r.weight, r.limit) === "breach") ? "breach" : "near"} />
                {flagged.map((r) => r.label).join(", ")} {flagged.length === 1 ? "è" : "sono"} sopra l'80% della soglia
              </p>
            )}
            <ul className="space-y-px">
              {rows.map((r) => (
                <Row key={r.label} label={r.label} row={r} scale={scale} sub={r.sub} />
              ))}
            </ul>
          </>
        )}
        {cash && !q.isPending && (
          <div className="mt-1.5 border-t border-line/70 pt-1.5">
            <ul>
              <Row label="Cassa" sub={fmtMoney(cash.value, { decimals: 0 })} row={{ value: cash.value, weight: cash.weight, limit: cash.min_reserve }} scale={Math.max(1, cash.weight)} min />
            </ul>
          </div>
        )}
      </div>
      <SourceNote sourced={q.data} className="px-4 pb-3" />
    </section>
  );
}
