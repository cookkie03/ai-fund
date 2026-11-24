import type { CSSProperties } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { direction, DOSSIER_STATUS, fmtScore, PROPOSAL_STATUS } from "./labels";

/** Direction as a soft-tinted tag: green and red only because direction is market meaning. */
export function DirectionTag({ value, className }: { value: string | null | undefined; className?: string }) {
  const d = direction(value);
  if (!d) return <span className={cn("text-2xs text-fg-subtle", className)}>—</span>;
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-5 rounded-tag px-1.5 text-2xs font-semibold border-transparent",
        d.tone === "up" ? "bg-up-soft text-up" : d.tone === "down" ? "bg-down-soft text-down" : "bg-hover text-fg-muted",
        className,
      )}
    >
      {d.label}
    </Badge>
  );
}

/** Proposal lifecycle. Pending waits on the PM (warn); the rest are quiet words. */
export function ProposalTag({ status, className }: { status: string | null | undefined; className?: string }) {
  if (!status) return <span className={cn("text-2xs text-fg-subtle", className)}>Nessuna</span>;
  const tone =
    status === "pending" ? "bg-warn-soft text-warn" : status === "accepted" ? "bg-up-soft text-up" : status === "rejected" ? "bg-down-soft text-down" : "bg-hover text-fg-muted";
  return (
    <Badge variant="outline" className={cn("h-5 whitespace-nowrap rounded-tag px-1.5 text-2xs font-medium border-transparent", tone, className)}>
      {PROPOSAL_STATUS[status] ?? status}
    </Badge>
  );
}

export function DossierStatusText({ status, className }: { status: string | null | undefined; className?: string }) {
  if (!status) return null;
  return <span className={cn("whitespace-nowrap text-xs text-fg-muted", className)}>{DOSSIER_STATUS[status] ?? status}</span>;
}

/**
 * A 0..1 score (conviction, confidence) as two decimals and a 4 px track. The track takes the author's
 * colour when one is given, so a fact's confidence reads as that author's mark.
 */
export function Score({ value, color, label, className, track = true }: { value: number | null | undefined; color?: string; label?: string; className?: string; track?: boolean }) {
  if (value === null || value === undefined) return <span className={cn("text-2xs text-fg-subtle", className)}>—</span>;
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)} aria-label={label ? `${label} ${fmtScore(value)}` : undefined}>
      <span className="num text-xs text-fg">{fmtScore(value)}</span>
      {track && (
        <span aria-hidden className="relative h-1 w-10 overflow-hidden rounded-tag bg-[oklch(0_0_0/0.35)]">
          <span className="absolute inset-y-0 left-0 rounded-tag" style={{ width: `${pct}%`, backgroundColor: color ?? "var(--fg-muted)" } as CSSProperties} />
        </span>
      )}
    </span>
  );
}
