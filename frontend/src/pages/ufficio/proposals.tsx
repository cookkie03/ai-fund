import { ArrowUpRight, Inbox } from "lucide-react";
import { Link } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { DecideProposal } from "@/features/dossier/decide-proposal";
import { useProposals } from "@/features/dossier/hooks";
import { fmtFraction, fmtRR, fmtScore } from "@/features/dossier/labels";
import { DirectionTag } from "@/features/dossier/parts";
import type { Proposal } from "@/features/dossier/types";
import { author } from "@/lib/authors";
import { fmtAge, fmtDateTime, parseTs } from "@/lib/format";
import { useNow } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";

/** Proposals waiting on the PM, oldest first: the longest wait is the first thing to read. */
export function usePendingProposals() {
  const q = useProposals({ status: "pending" });
  const list = q.data?.state === "ok" ? [...q.data.data].sort((a, b) => (parseTs(a.submitted_ts) ?? 0) - (parseTs(b.submitted_ts) ?? 0)) : [];
  return { q, list };
}

function Row({ p, now, focused, dimmed, onFocus }: { p: Proposal; now: number; focused?: boolean; dimmed?: boolean; onFocus?: (t: string | null) => void }) {
  const waited = parseTs(p.submitted_ts);
  const agent = author(p.agent || `ticker:${p.ticker}`);
  const lowRR = p.risk_reward !== null && p.risk_reward < 1.5;
  return (
    <li
      onMouseEnter={() => onFocus?.(p.ticker)}
      onMouseLeave={() => onFocus?.(null)}
      className={cn("group rounded-item px-2.5 py-2 transition-[background-color,opacity] duration-150", focused ? "bg-hover" : "hover:bg-hover", dimmed && "opacity-45")}
    >
      <div className="flex min-w-0 items-center gap-2">
        <AuthorChip author={agent} size="xs" tooltip={`${agent.name}: ha proposto ${p.ticker}`} />
        <Link to={`/ticker/${p.ticker}`} className="text-[13px] font-semibold tracking-[-0.005em] text-fg outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/60">
          {p.ticker}
        </Link>
        <DirectionTag value={p.direction} />
        <span className="num ml-auto shrink-0 text-2xs text-fg-subtle" title={`Inviata ${fmtDateTime(p.submitted_ts)}`}>
          {waited ? `da ${fmtAge(waited, now)}` : "—"}
        </span>
      </div>
      <div className="mt-1.5 flex items-center gap-3 pl-[26px] text-2xs text-fg-subtle">
        <span>
          conv. <span className="num text-xs text-fg">{fmtScore(p.conviction)}</span>
        </span>
        <span>
          sizing <span className="num text-xs text-fg">{fmtFraction(p.sizing_fraction)}</span>
        </span>
        <span>
          R:R <span className={cn("num text-xs", lowRR ? "text-warn" : "text-fg")}>{fmtRR(p.risk_reward)}</span>
        </span>
        <DecideProposal
          proposal={p}
          trigger={
            <Button variant="ghost" size="xs" className="-my-1 ml-auto -mr-1.5 text-fg-muted hover:text-fg" aria-label={`Decidi la proposta su ${p.ticker}`}>
              Decidi
            </Button>
          }
        />
      </div>
    </li>
  );
}

/**
 * The PM's queue. Rendered inside a tile (overview, PM agent view, phone). `focus` and `onFocus` join the
 * office's cross-highlight: hovering a proposal lights its ticker on the desk.
 */
export function PendingProposals({ className, focus, onFocus, dense = false }: { className?: string; focus?: string | null; onFocus?: (t: string | null) => void; dense?: boolean }) {
  const { q, list } = usePendingProposals();
  const now = useNow(30_000);
  if (q.isPending)
    return (
      <div className={cn("space-y-1 px-1.5", className)} aria-busy aria-label="Caricamento delle proposte">
        {[0, 1].map((i) => (
          <div key={i} className="space-y-2 px-2.5 py-2.5">
            <span className="block h-3 w-1/2 animate-pulse rounded-tag bg-hover" />
            <span className="block h-2.5 w-3/4 animate-pulse rounded-tag bg-hover" />
          </div>
        ))}
      </div>
    );
  if (q.isError) return <p className={cn("px-4 py-2 text-xs text-down", className)}>Proposte non disponibili: {q.error.message}</p>;
  if (q.data.state === "unavailable")
    return (
      <p className={cn("px-4 py-3 text-xs leading-relaxed text-fg-muted", className)}>
        Le proposte degli agenti del ticker compariranno qui quando il Runtime esporrà <code className="num rounded-tag bg-hover px-1 text-2xs text-fg">{q.data.endpoint}</code>.
      </p>
    );
  if (list.length === 0)
    return (
      <div className={cn("flex items-center gap-2.5 px-4 py-3 text-xs text-fg-subtle", className)}>
        <Inbox className="size-4 shrink-0" strokeWidth={1.5} aria-hidden />
        <span>Nessuna proposta in attesa: il PM ha deciso su tutte.</span>
      </div>
    );
  return (
    <ol className={cn("space-y-px px-1.5", className)}>
      {(dense ? list.slice(0, 6) : list).map((p) => (
        <Row key={p.id} p={p} now={now} focused={focus === p.ticker} dimmed={!!focus && focus !== p.ticker} onFocus={onFocus} />
      ))}
      {dense && list.length > 6 && (
        <li className="px-2.5 pt-1">
          <Link to="/ufficio/portfolio_manager" className="inline-flex items-center gap-1 text-2xs text-fg-subtle hover:text-fg">
            Altre {list.length - 6} nella coda del PM <ArrowUpRight className="size-3" aria-hidden />
          </Link>
        </li>
      )}
    </ol>
  );
}
