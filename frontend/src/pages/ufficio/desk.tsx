import { ChevronRight, FileText, History, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useDossiers } from "@/features/dossier/hooks";
import { DOSSIER_STATUS, fmtScore } from "@/features/dossier/labels";
import { DirectionTag, ProposalTag } from "@/features/dossier/parts";
import type { DossierSummary } from "@/features/dossier/types";
import type { OfficeAgent } from "@/features/office/types";
import { author, tickerAgentId } from "@/lib/authors";
import { fmtAge, fmtWhen, parseTs } from "@/lib/format";
import { usePortfolio } from "@/lib/runtime/hooks";
import { useNow } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { fmtCost, onRadioKeys, StatusMark, STATUS_LABEL } from "./parts";

export type Focus = { ticker: string | null; agent: string | null };
export const NO_FOCUS: Focus = { ticker: null, agent: null };

export type DeskRow = {
  ticker: string;
  agent: OfficeAgent | null;
  summary: DossierSummary | null;
  /** Specialists whose current work is on this ticker: who the ticker agent is calling on right now. */
  specialists: OfficeAgent[];
  pending: boolean;
  invested: boolean;
  analyzing: boolean;
  idle: boolean;
  last: number | null;
};

export type DeskFilter = "all" | "analyzing" | "pending" | "invested" | "idle";

const FILTERS: { id: DeskFilter; label: string }[] = [
  { id: "all", label: "Tutti" },
  { id: "analyzing", label: "In analisi" },
  { id: "pending", label: "In attesa del PM" },
  { id: "invested", label: "In portafoglio" },
  { id: "idle", label: "Inattivi" },
];

/**
 * One row per ticker: its agent (`kind: "ticker"` in agents), its dossier summary (`dossiers`), and the
 * specialists working on it. A ticker with a dossier but no agent still shows, marked as such.
 */
export function useDeskRows(agents: OfficeAgent[], pendingTickers: Set<string>) {
  const dossiers = useDossiers();
  const portfolio = usePortfolio();
  const rows = useMemo(() => {
    const summaries = dossiers.data?.state === "ok" ? dossiers.data.data : [];
    const held = new Set((portfolio.data?.positions ?? []).map((p) => (p.symbol ?? p.ticker ?? "").toUpperCase()).filter(Boolean));
    const tickerAgents = agents.filter((a) => a.kind === "ticker" && a.ticker);
    const specialists = agents.filter((a) => a.kind === "core" && a.name !== "portfolio_manager" && a.name !== "subagent");
    const symbols = Array.from(new Set([...tickerAgents.map((a) => a.ticker!), ...summaries.map((s) => s.ticker)]));
    return symbols.map<DeskRow>((ticker) => {
      const agent = tickerAgents.find((a) => a.ticker === ticker) ?? null;
      const summary = summaries.find((s) => s.ticker === ticker) ?? null;
      const pending = pendingTickers.has(ticker) || summary?.proposal_status === "pending";
      const analyzing = summary?.status === "analyzing" || (!pending && agent?.status === "working");
      const invested = summary ? summary.invested : held.has(ticker);
      return {
        ticker,
        agent,
        summary,
        specialists: specialists.filter((s) => s.current?.ticker === ticker),
        pending,
        invested,
        analyzing,
        idle: !pending && !analyzing && (!agent || agent.status === "idle" || agent.status === null),
        last: parseTs(agent?.last_activity_ts) ?? parseTs(summary?.updated_ts),
      };
    });
  }, [agents, dossiers.data, portfolio.data, pendingTickers]);
  return { rows, dossiers };
}

const rank = (r: DeskRow) => (r.pending ? 0 : r.agent?.status === "working" ? 1 : r.agent?.status === "waiting" ? 2 : r.analyzing ? 3 : 4);

function sortRows(rows: DeskRow[]) {
  return [...rows].sort((a, b) => rank(a) - rank(b) || (b.last ?? 0) - (a.last ?? 0) || a.ticker.localeCompare(b.ticker));
}

export function matches(r: DeskRow, f: DeskFilter) {
  return f === "all" || (f === "analyzing" && r.analyzing) || (f === "pending" && r.pending) || (f === "invested" && r.invested) || (f === "idle" && r.idle);
}

export function isLit(r: DeskRow, focus: Focus, agents: OfficeAgent[]) {
  if (focus.ticker) return focus.ticker === r.ticker;
  if (focus.agent) return agents.find((a) => a.name === focus.agent)?.current?.ticker === r.ticker;
  return false;
}

function StateCell({ r }: { r: DeskRow }) {
  if (!r.agent)
    return (
      <span className="flex min-w-0 items-center gap-1.5 text-xs text-fg-subtle">
        <span aria-hidden className="inline-block size-2 shrink-0 rounded-full shadow-[inset_0_0_0_1.5px_var(--line-strong)]" />
        Nessun agente
      </span>
    );
  // "Proposta al PM" would repeat the Proposta column: then the agent's own state says more.
  const fromAgent = !r.summary || r.summary.status === "proposed";
  const word = fromAgent ? (r.agent.status ? STATUS_LABEL[r.agent.status] : "—") : (DOSSIER_STATUS[r.summary!.status] ?? r.summary!.status);
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      {r.agent.status && <StatusMark agent={r.agent.name} status={r.agent.status} compact />}
      <span className="shrink-0 text-xs text-fg-muted">{word}</span>
      {r.agent.current?.label && <span className="hidden min-w-0 truncate text-xs text-fg-subtle @[50rem]/desk:inline">· {r.agent.current.label}</span>}
    </span>
  );
}

function Specialists({ list }: { list: OfficeAgent[] }) {
  if (!list.length) return <span className="text-2xs text-fg-faint" aria-label="Nessuno specialist al lavoro">—</span>;
  return (
    <span className="flex -space-x-1">
      {list.slice(0, 4).map((s) => (
        <AuthorChip key={s.name} actor={s.name} size="xs" className="rounded-full ring-2 ring-ground" tooltip={`${author(s.name).name} lavora su questo ticker`} />
      ))}
    </span>
  );
}

function StaleTag({ n }: { n: number }) {
  if (!n) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="num inline-flex h-4 shrink-0 items-center gap-0.5 rounded-tag bg-warn-soft px-1 text-[10px] text-warn" aria-label={`${n} fatti vecchi`}>
          <History className="size-2.5" strokeWidth={2} aria-hidden />
          {n}
        </span>
      </TooltipTrigger>
      <TooltipContent>{n === 1 ? "Un fatto della scheda è vecchio" : `${n} fatti della scheda sono vecchi`}: da rivedere al prossimo ciclo</TooltipContent>
    </Tooltip>
  );
}

function DossierLink({ ticker }: { ticker: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          to={`/ticker/${ticker}`}
          aria-label={`Apri la scheda di ${ticker}`}
          className="relative z-10 grid size-7 place-items-center rounded-item text-fg-subtle outline-none transition-colors hover:bg-raised hover:text-fg focus-visible:ring-2 focus-visible:ring-ring/60"
        >
          <FileText className="size-[15px]" strokeWidth={1.75} />
        </Link>
      </TooltipTrigger>
      <TooltipContent>Scheda di {ticker}</TooltipContent>
    </Tooltip>
  );
}

function DeskLine({ r, now, usageKnown, lit, dimmed, onFocus }: { r: DeskRow; now: number; usageKnown: boolean; lit: boolean; dimmed: boolean; onFocus: (f: Focus) => void }) {
  const to = r.agent ? `/ufficio/${r.agent.name}` : `/ticker/${r.ticker}`;
  return (
    <li
      data-ticker={r.ticker}
      onMouseEnter={() => onFocus({ ticker: r.ticker, agent: null })}
      onMouseLeave={() => onFocus(NO_FOCUS)}
      className={cn("relative flex h-10 items-center gap-3 rounded-item px-2.5 transition-[background-color,opacity] duration-150", lit ? "bg-hover" : "hover:bg-hover", dimmed && "opacity-40")}
    >
      <span className="flex w-[104px] shrink-0 items-center gap-2">
        <AuthorChip actor={tickerAgentId(r.ticker)} size="xs" className="shrink-0" tooltip={r.agent ? author(r.agent.name).name : `${r.ticker}: nessun agente del ticker`} />
        <Link to={to} className="text-[13px] font-semibold tracking-[-0.005em] text-fg outline-none after:absolute after:inset-0 after:rounded-item focus-visible:after:ring-2 focus-visible:after:ring-ring/60">
          {r.ticker}
        </Link>
        <StaleTag n={r.summary?.stale_count ?? 0} />
      </span>
      <span className="min-w-0 flex-1">
        <StateCell r={r} />
      </span>
      <span className="flex w-[96px] shrink-0 items-center gap-1.5">
        {r.summary?.direction ? (
          <>
            <DirectionTag value={r.summary.direction} />
            <span className="num text-xs text-fg-muted">{fmtScore(r.summary.conviction)}</span>
          </>
        ) : (
          <span className="text-2xs text-fg-subtle">{r.summary ? "Nessuna tesi" : "—"}</span>
        )}
      </span>
      <span className="w-[124px] shrink-0">{r.summary || r.pending ? <ProposalTag status={r.pending ? "pending" : r.summary?.proposal_status} /> : <span className="text-2xs text-fg-subtle">—</span>}</span>
      <span className="hidden w-[60px] shrink-0 @[42rem]/desk:flex">
        <Specialists list={r.specialists} />
      </span>
      {usageKnown && <span className="num hidden w-[58px] shrink-0 text-right text-xs text-fg-muted @[38rem]/desk:block">{r.agent?.today ? fmtCost(r.agent.today.cost) : "—"}</span>}
      <span className="num w-[52px] shrink-0 text-right text-2xs text-fg-subtle" title={r.last ? fmtWhen(r.last, now) : undefined}>
        {r.last ? fmtAge(r.last, now) : "—"}
      </span>
      <DossierLink ticker={r.ticker} />
    </li>
  );
}

function MobileDeskLine({ r, now }: { r: DeskRow; now: number }) {
  const to = r.agent ? `/ufficio/${r.agent.name}` : `/ticker/${r.ticker}`;
  return (
    <li className="relative flex min-h-[60px] items-center gap-3 rounded-item px-2.5 py-2 active:bg-hover">
      <AuthorChip actor={tickerAgentId(r.ticker)} size="md" />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <Link to={to} className="text-[13px] font-semibold text-fg outline-none after:absolute after:inset-0 after:rounded-item">
            {r.ticker}
          </Link>
          {r.summary?.direction && <DirectionTag value={r.summary.direction} />}
          {r.summary?.conviction != null && <span className="num text-xs text-fg-muted">{fmtScore(r.summary.conviction)}</span>}
          <StaleTag n={r.summary?.stale_count ?? 0} />
        </span>
        <span className="mt-1 flex items-center gap-2">
          <StateCell r={r} />
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1">
        {(r.pending || r.summary?.proposal_status) && <ProposalTag status={r.pending ? "pending" : r.summary?.proposal_status} />}
        <span className="num text-2xs text-fg-subtle">{r.last ? fmtAge(r.last, now) : "—"}</span>
      </span>
      <ChevronRight className="size-4 shrink-0 text-fg-subtle" aria-hidden />
    </li>
  );
}

/** The desk of ticker agents: dense, filterable, 3 to 40 rows. Reports to the PM (`supervisor`). */
export function TickerDesk({
  agents,
  pendingTickers,
  usageKnown,
  focus,
  onFocus,
  mobile = false,
  className,
}: {
  agents: OfficeAgent[] | null;
  pendingTickers: Set<string>;
  usageKnown: boolean;
  focus: Focus;
  onFocus: (f: Focus) => void;
  mobile?: boolean;
  className?: string;
}) {
  const [filter, setFilter] = useState<DeskFilter>("all");
  const [text, setText] = useState("");
  const now = useNow(15_000);
  const { rows, dossiers } = useDeskRows(agents ?? [], pendingTickers);
  const sorted = sortRows(rows);
  const needle = text.trim().toUpperCase();
  const shown = sorted.filter((r) => matches(r, filter) && (!needle || r.ticker.includes(needle)));
  const counts = Object.fromEntries(FILTERS.map((f) => [f.id, rows.filter((r) => matches(r, f.id)).length])) as Record<DeskFilter, number>;
  const supervisor = agents?.find((a) => a.kind === "ticker" && a.supervisor)?.supervisor ?? null;
  // A Runtime that predates the contract sends no `kind`: no ticker agents and no dossiers can be told apart from "none yet".
  const contract = (agents ?? []).some((a) => a.kind === "ticker") || dossiers.data?.state === "ok";

  const header = (
    <header className="flex min-h-11 shrink-0 flex-wrap items-center gap-x-2 gap-y-1.5 py-1.5 pl-4 pr-2">
      <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">Desk dei ticker</h2>
      {rows.length > 0 && <span className="num rounded-tag bg-hover px-1.5 text-[10px] leading-4 text-fg-subtle">{rows.length}</span>}
      {supervisor && (
        <span className="inline-flex items-center gap-1.5 text-2xs text-fg-subtle">
          riporta a <AuthorChip actor={supervisor} size="xs" label tooltip={`Supervisore: ${author(supervisor).name}`} />
        </span>
      )}
      {rows.length > 10 && (
        <label className="relative ml-auto flex items-center">
          <Search className="pointer-events-none absolute left-2 size-3.5 text-fg-subtle" aria-hidden />
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Filtra ticker"
            aria-label="Filtra ticker"
            spellCheck={false}
            className="num h-7 w-32 rounded-control border border-line-strong bg-ground pl-7 pr-2 text-xs uppercase text-fg outline-none placeholder:normal-case placeholder:text-fg-subtle focus:border-accent-c/70"
          />
        </label>
      )}
    </header>
  );

  const filterBar = rows.length > 0 && (
    <div className={cn("shrink-0 px-3 pb-2", mobile && "-mx-0 overflow-x-auto")}>
      <div role="radiogroup" aria-label="Filtra il desk" className="seg" onKeyDown={onRadioKeys}>
        {FILTERS.map((f) => (
          <button key={f.id} type="button" role="radio" aria-checked={filter === f.id} tabIndex={filter === f.id ? 0 : -1} onClick={() => setFilter(f.id)} className="seg-item" disabled={f.id !== "all" && counts[f.id] === 0}>
            {f.label}
            <span className={cn("num rounded-tag px-1 text-[10px] leading-4", f.id === "pending" && counts.pending > 0 ? "bg-warn-soft text-warn" : "bg-hover text-fg-subtle")}>{counts[f.id]}</span>
          </button>
        ))}
      </div>
    </div>
  );

  let body;
  if (agents === null || dossiers.isPending) {
    body = (
      <div className="space-y-1 px-1.5 pb-2" aria-busy aria-label="Caricamento del desk">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="flex h-10 items-center gap-3 px-2.5">
            <span className="size-[18px] animate-pulse rounded-full bg-hover" />
            <span className="h-3 w-14 animate-pulse rounded-tag bg-hover" />
            <span className="h-3 flex-1 animate-pulse rounded-tag bg-hover" />
          </div>
        ))}
      </div>
    );
  } else if (!contract && rows.length === 0) {
    body = (
      <p className="px-4 pb-4 pt-1 text-xs leading-relaxed text-fg-muted">
        Il Runtime non espone ancora gli agenti del ticker: servono <code className="num rounded-tag bg-hover px-1 text-2xs text-fg">kind</code>, <code className="num rounded-tag bg-hover px-1 text-2xs text-fg">ticker</code> e{" "}
        <code className="num rounded-tag bg-hover px-1 text-2xs text-fg">supervisor</code> in <code className="num rounded-tag bg-hover px-1 text-2xs text-fg">GET /v1/read/agents</code> e <code className="num rounded-tag bg-hover px-1 text-2xs text-fg">GET /v1/read/dossiers</code>.
      </p>
    );
  } else if (rows.length === 0) {
    body = <p className="px-4 pb-5 pt-1 text-xs leading-relaxed text-fg-subtle">Nessun agente del ticker. Nasce alla prima apertura di un ciclo su un ticker: assegna un task al PM per cominciare.</p>;
  } else if (shown.length === 0) {
    body = <p className="px-4 pb-5 pt-1 text-xs text-fg-subtle">Nessun ticker {needle ? `con «${needle}»` : "in questo filtro"}.</p>;
  } else if (mobile) {
    body = (
      <ul className="space-y-px px-1.5 pb-1.5">
        {shown.map((r) => (
          <MobileDeskLine key={r.ticker} r={r} now={now} />
        ))}
      </ul>
    );
  } else {
    body = (
      <div className="px-1.5 pb-2">
        <div aria-hidden className="flex h-7 items-center gap-3 px-2.5 text-2xs text-fg-subtle">
          <span className="w-[104px] shrink-0">Ticker</span>
          <span className="min-w-0 flex-1">Stato</span>
          <span className="w-[96px] shrink-0">Tesi</span>
          <span className="w-[124px] shrink-0">Proposta</span>
          <span className="hidden w-[60px] shrink-0 @[42rem]/desk:block">Specialist</span>
          {usageKnown && <span className="hidden w-[58px] shrink-0 text-right @[38rem]/desk:block">Costo oggi</span>}
          <span className="w-[52px] shrink-0 text-right">Attività</span>
          <span className="w-7 shrink-0" />
        </div>
        <ul aria-label="Agenti del ticker" className="space-y-px">
          {shown.map((r) => {
            const lit = isLit(r, focus, agents);
            return <DeskLine key={r.ticker} r={r} now={now} usageKnown={usageKnown} lit={lit} dimmed={(!!focus.ticker || !!focus.agent) && !lit} onFocus={onFocus} />;
          })}
        </ul>
      </div>
    );
  }

  return (
    <section aria-label="Desk dei ticker" className={cn("@container/desk flex min-h-0 flex-col rounded-tile bg-ground", className)}>
      {header}
      {filterBar}
      {body}
      {contract && dossiers.data?.state === "unavailable" && rows.length > 0 && (
        <p className="px-4 pb-3 text-2xs leading-4 text-fg-subtle">Tesi e proposte compariranno quando il Runtime esporrà {dossiers.data.endpoint}.</p>
      )}
    </section>
  );
}
