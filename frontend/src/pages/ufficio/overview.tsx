import { ChevronDown, ChevronRight, ListPlus } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { PERIOD_LABEL, useOfficeAgents, useRecentMessages, useUsage, type RecentMessage, type UsagePeriod } from "@/features/office/hooks";
import type { OfficeAgent, UsageRow, UsageTotals } from "@/features/office/types";
import { AGENT_IDS, author, tickerOf } from "@/lib/authors";
import { fmtAge, fmtWhen, parseTs } from "@/lib/format";
import { useNow } from "@/lib/runtime/provider";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { AssignTask } from "./assign-task";
import { NO_FOCUS, TickerDesk, type Focus } from "./desk";
import { fmtCost, fmtTokens, Meter, ROLE, SourceNote, StatusMark, TickerTag, totalTokens, onRadioKeys } from "./parts";
import { PendingProposals, usePendingProposals } from "./proposals";

/** Specialists keep the office's canonical order so the column never reshuffles under the eye. */
const canonical = (x: OfficeAgent, y: OfficeAgent) => (AGENT_IDS.indexOf(x.name) + 100 * +(x.name === "subagent")) - (AGENT_IDS.indexOf(y.name) + 100 * +(y.name === "subagent"));

function useTodayUsage(): (agent: OfficeAgent) => UsageTotals | null {
  const usage = useUsage(null, "today");
  const rows = usage.data?.source === "runtime" ? usage.data.data : null;
  return (a) => a.today ?? rows?.find((r) => r.agent === a.name) ?? null;
}

function workLine(a: OfficeAgent) {
  const c = a.current;
  if (!c) return <span className="text-fg-subtle">{a.status === "idle" ? "Nessun task: aspetta il prossimo trigger" : "Nessun task in corso"}</span>;
  const kind = c.kind === "cycle" ? "Ciclo" : "Task";
  return (
    <span className="flex min-w-0 items-center gap-2">
      {c.ticker && <TickerTag ticker={c.ticker} />}
      <span className="min-w-0 truncate text-fg-muted">{c.label ?? `${kind}${c.id !== null ? ` #${c.id}` : ""} aperto`}</span>
    </span>
  );
}

/**
 * The PM's seat with its queue inside it: the proposals waiting on the PM are literally part of its desk.
 * The ticker agents report here; Luca can decide in the PM's place.
 */
function PmSeat({ a, today, now, usageKnown, said, focus, onFocus, className }: { a: OfficeAgent | undefined; today: UsageTotals | null; now: number; usageKnown: boolean; said?: RecentMessage; focus: Focus; onFocus: (f: Focus) => void; className?: string }) {
  const { list } = usePendingProposals();
  const who = author("portfolio_manager");
  const last = parseTs(a?.last_activity_ts);
  return (
    <section aria-label="Portfolio Manager" className={cn("flex min-h-0 flex-col rounded-tile bg-ground", className)}>
      <div className="group relative shrink-0 p-4 pb-3">
        <div className="flex items-start gap-3">
          <AuthorChip author={who} size="lg" tooltip={`${who.name}${a?.model ? ` · ${a.model}` : ""}`} />
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-[13px] font-semibold text-fg">
              <Link to="/ufficio/portfolio_manager" className="outline-none after:absolute after:inset-0 after:rounded-t-tile focus-visible:after:ring-2 focus-visible:after:ring-ring/70">
                {who.name}
              </Link>
            </h2>
            <p className="truncate text-2xs text-fg-subtle">{ROLE.portfolio_manager}</p>
          </div>
          {a?.status && <StatusMark agent={a.name} status={a.status} />}
        </div>
        {a ? (
          <>
            <div className="mt-3 flex h-6 min-w-0 items-center text-xs">{workLine(a)}</div>
            {said && (
              <p className="mt-1.5 line-clamp-2 text-xs leading-4 text-fg-subtle">
                <span className="text-fg-muted">«{said.text}»</span> <span className="num whitespace-nowrap">in {said.ticker}</span>
              </p>
            )}
            <dl className="mt-3 grid grid-cols-3 gap-3">
              <Meter label="Ultima attività" value={last ? `${fmtAge(last, now)} fa` : "—"} hint={last ? fmtWhen(a.last_activity_ts, now) : "Nessuna attività registrata"} />
              {usageKnown && (
                <>
                  <Meter label="Costo oggi" value={fmtCost(today?.cost ?? 0)} />
                  <Meter label="Token oggi" value={fmtTokens(totalTokens(today) ?? 0)} hint={today ? `${fmtTokens(today.tokens_in)} in · ${fmtTokens(today.tokens_out)} out · ${today.calls} chiamate` : undefined} />
                </>
              )}
            </dl>
          </>
        ) : (
          <p className="mt-3 text-xs text-fg-subtle">Il Runtime non ha mandato lo stato del PM.</p>
        )}
      </div>
      <div className="flex min-h-0 flex-1 flex-col pb-1.5">
        <h3 className="flex h-9 shrink-0 items-center gap-2 px-4 text-[13px] font-semibold tracking-[-0.005em] text-fg">
          In attesa del PM
          {list.length > 0 && <span className="num rounded-tag bg-warn-soft px-1.5 text-[10px] leading-4 text-warn">{list.length}</span>}
        </h3>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <PendingProposals focus={focus.ticker} onFocus={(t) => onFocus(t ? { ticker: t, agent: null } : NO_FOCUS)} />
        </div>
      </div>
    </section>
  );
}

/** A specialist as a compact seat: who, status, the ticker they are on. Hover lights that ticker on the desk. */
function SpecialistRow({ a, today, now, usageKnown, lit, dimmed, onFocus }: { a: OfficeAgent; today: UsageTotals | null; now: number; usageKnown: boolean; lit: boolean; dimmed: boolean; onFocus: (f: Focus) => void }) {
  const who = author(a.name);
  const last = parseTs(a.last_activity_ts);
  const quiet = a.name === "subagent";
  return (
    <li
      onMouseEnter={() => onFocus({ ticker: null, agent: a.name })}
      onMouseLeave={() => onFocus(NO_FOCUS)}
      className={cn("group relative rounded-item px-2.5 py-2 transition-[background-color,opacity] duration-150", lit ? "bg-hover" : "hover:bg-hover", dimmed && "opacity-40")}
    >
      <div className="flex items-center gap-2.5">
        <AuthorChip author={who} size="md" tooltip={`${who.name}${a.model ? ` · ${a.model}` : ""}`} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <Link to={`/ufficio/${a.name}`} className={cn("truncate text-[13px] font-semibold outline-none after:absolute after:inset-0 after:rounded-item focus-visible:after:ring-2 focus-visible:after:ring-ring/60", quiet ? "text-fg-muted" : "text-fg")}>
              {who.name}
            </Link>
            {a.status && <StatusMark agent={a.name} status={a.status} compact />}
            <span className="num ml-auto shrink-0 text-2xs text-fg-subtle">{usageKnown ? fmtCost(today?.cost ?? 0) : last ? fmtAge(last, now) : ""}</span>
          </div>
          <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs">
            {a.current?.ticker && <TickerTag ticker={a.current.ticker} className="h-4 px-1 text-[10px]" />}
            <span className="min-w-0 truncate text-fg-subtle">{a.current ? (a.current.label ?? (a.current.kind === "cycle" ? "Ciclo aperto" : "Task in corso")) : (a.role && a.role !== a.name ? a.role : (ROLE[a.name] ?? "Agente"))}</span>
          </div>
        </div>
      </div>
      <div className="relative z-10 mt-1 hidden pl-[38px] group-focus-within:block group-hover:block">
        <AssignTask
          agent={a.name}
          ticker={a.current?.ticker ?? null}
          align="start"
          trigger={
            <Button variant="ghost" size="xs" className="-ml-2 text-fg-muted">
              <ListPlus /> Assegna task
            </Button>
          }
        />
      </div>
    </li>
  );
}

function SpecialistsTile({ list, todayOf, now, usageKnown, focus, onFocus, className }: { list: OfficeAgent[]; todayOf: (a: OfficeAgent) => UsageTotals | null; now: number; usageKnown: boolean; focus: Focus; onFocus: (f: Focus) => void; className?: string }) {
  const active = !!focus.ticker || !!focus.agent;
  return (
    <section aria-label="Specialist" className={cn("shrink-0 rounded-tile bg-ground", className)}>
      <header className="flex h-11 items-center gap-2 pl-4 pr-3">
        <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">Specialist</h2>
        <span className="ml-auto text-2xs text-fg-subtle">chiamati dagli agenti del ticker</span>
      </header>
      <ul className="space-y-px px-1.5 pb-1.5">
        {list.map((a) => {
          const lit = focus.agent === a.name || (!!focus.ticker && a.current?.ticker === focus.ticker);
          return <SpecialistRow key={a.name} a={a} today={todayOf(a)} now={now} usageKnown={usageKnown} lit={lit} dimmed={active && !lit} onFocus={onFocus} />;
        })}
      </ul>
    </section>
  );
}

/** What the agents said last, across recent cycles: a way into a conversation without picking an agent first. */
function RecentActivity({ className }: { className?: string }) {
  const q = useRecentMessages(16);
  const now = useNow(30_000);
  return (
    <section aria-label="Conversazioni recenti" className={cn("flex min-h-0 flex-col rounded-tile bg-ground", className)}>
      <header className="flex h-11 shrink-0 items-center gap-2 pl-4 pr-3">
        <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">Conversazioni recenti</h2>
        <span className="ml-auto text-2xs text-fg-subtle">dai cicli di analisi</span>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
        {q.isPending ? (
          <div className="space-y-1 px-1" aria-busy aria-label="Caricamento delle conversazioni">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex gap-2.5 px-1.5 py-2">
                <span className="size-5 animate-pulse rounded-full bg-hover" />
                <span className="flex-1 space-y-1.5">
                  <span className="block h-3 w-1/2 animate-pulse rounded-tag bg-hover" />
                  <span className="block h-2.5 w-5/6 animate-pulse rounded-tag bg-hover" />
                </span>
              </div>
            ))}
          </div>
        ) : q.isError ? (
          <p className="px-2.5 py-2 text-xs text-down">Conversazioni non disponibili: {q.error.message}</p>
        ) : q.data.length === 0 ? (
          <p className="px-2.5 py-6 text-center text-xs leading-relaxed text-fg-subtle">Nessun ciclo recente: quando gli agenti aprono un'analisi, le loro conversazioni compaiono qui.</p>
        ) : (
          <ol className="space-y-px">
            {q.data.map((m) => {
              const a = author(m.author);
              const linkable = a.kind === "agent";
              const body = (
                <>
                  <AuthorChip author={a} size="sm" className="mt-px" />
                  <span className="min-w-0 flex-1">
                    <span className="flex min-w-0 items-baseline gap-1.5">
                      <span className="truncate text-xs font-medium text-fg">{a.short}</span>
                      <span className="text-2xs text-fg-subtle">in</span>
                      <span className="num text-2xs font-semibold text-fg-muted">{m.ticker}</span>
                      <span className="num ml-auto shrink-0 text-2xs text-fg-subtle">{fmtWhen(m.ts, now)}</span>
                    </span>
                    <span className="mt-0.5 line-clamp-2 text-xs leading-4 text-fg-muted">{m.text}</span>
                  </span>
                </>
              );
              return (
                <li key={m.id}>
                  {linkable ? (
                    <Link
                      to={`/ufficio/${a.id}?chat=${encodeURIComponent(m.ticker)}`}
                      className="flex gap-2.5 rounded-item px-2.5 py-2 outline-none transition-colors duration-150 hover:bg-hover focus-visible:ring-2 focus-visible:ring-ring/60"
                    >
                      {body}
                    </Link>
                  ) : (
                    <div className="flex gap-2.5 px-2.5 py-2">{body}</div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </section>
  );
}

const PERIODS: UsagePeriod[] = ["today", "7d", "30d"];

function UsageLine({ name, label, r, share, max, total, pending, nested = false, color }: { name: string; label?: ReactNode; r: UsageRow | undefined; share: number; max: number; total: number; pending: boolean; nested?: boolean; color?: string }) {
  const who = author(name);
  return (
    <tr className="hover:[&>td]:bg-hover">
      <td className={cn("h-8 px-2.5 transition-colors", nested && "pl-8")}>{label ?? (
        <span className="flex items-center gap-2">
          <AuthorChip author={who} size="xs" />
          <span className="truncate text-fg">{who.name}</span>
        </span>
      )}</td>
      <td className="h-8 px-2.5 transition-colors">
        {pending ? (
          <span className="block h-1.5 w-full animate-pulse rounded-tag bg-hover" />
        ) : (
          <span className="flex items-center gap-2">
            <span className="relative h-1.5 flex-1 overflow-hidden rounded-tag bg-[oklch(0_0_0/0.3)]">
              <span className="absolute inset-y-0 left-0 rounded-tag" style={{ width: `${max > 0 && r ? (r.cost / max) * 100 : 0}%`, backgroundColor: color ?? who.color }} />
            </span>
            <span className="num w-9 text-right text-2xs text-fg-subtle">{total > 0 ? Math.round(share * 100) : 0}%</span>
          </span>
        )}
      </td>
      <td className="num h-8 px-2.5 text-right text-fg-muted transition-colors">{pending ? "…" : (r?.calls ?? 0)}</td>
      <td className="num h-8 px-2.5 text-right text-fg-muted transition-colors">{pending ? "…" : fmtTokens(r?.tokens_in ?? 0)}</td>
      <td className="num h-8 px-2.5 text-right text-fg-muted transition-colors">{pending ? "…" : fmtTokens(r?.tokens_out ?? 0)}</td>
      <td className="num h-8 px-2.5 text-right text-fg transition-colors">{pending ? "…" : fmtCost(r?.cost ?? 0)}</td>
    </tr>
  );
}

/**
 * Cost and tokens per agent for a period, read from the Runtime's LLM calls. The ticker agents fold into
 * one row (they can be 40) that opens to show each.
 */
function UsageTile({ order, className }: { order: string[]; className?: string }) {
  const [period, setPeriod] = useState<UsagePeriod>("today");
  const [openTickers, setOpenTickers] = useState(false);
  const q = useUsage(null, period);
  const rows = q.data?.source === "runtime" ? q.data.data : [];
  const coreRows = rows.filter((r) => !tickerOf(r.agent));
  const tickerRows = rows.filter((r) => tickerOf(r.agent)).sort((a, b) => b.cost - a.cost);
  const byAgent = new Map(coreRows.map((r) => [r.agent, r]));
  const names = [...order, ...coreRows.map((r) => r.agent).filter((n) => !order.includes(n))];
  const total = rows.reduce((acc, r) => ({ cost: acc.cost + r.cost, tin: acc.tin + r.tokens_in, tout: acc.tout + r.tokens_out, calls: acc.calls + r.calls }), { cost: 0, tin: 0, tout: 0, calls: 0 });
  const tickerSum: UsageRow = tickerRows.reduce((acc, r) => ({ ...acc, cost: acc.cost + r.cost, tokens_in: acc.tokens_in + r.tokens_in, tokens_out: acc.tokens_out + r.tokens_out, calls: acc.calls + r.calls }), { agent: "ticker:*", cost: 0, tokens_in: 0, tokens_out: 0, calls: 0 });
  const max = Math.max(0, ...coreRows.map((r) => r.cost), tickerSum.cost);
  return (
    <section aria-label="Costi e token" className={cn("rounded-tile bg-ground", className)}>
      <header className="flex h-11 items-center gap-2 pl-4 pr-2">
        <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">Costi e token</h2>
        <div role="radiogroup" aria-label="Periodo" className="seg ml-auto" onKeyDown={onRadioKeys}>
          {PERIODS.map((p) => (
            <button key={p} type="button" role="radio" aria-checked={period === p} tabIndex={period === p ? 0 : -1} onClick={() => setPeriod(p)} className="seg-item" disabled={q.data?.source === "unavailable"}>
              {PERIOD_LABEL[p]}
            </button>
          ))}
        </div>
      </header>
      {q.data?.source === "unavailable" ? (
        <p className="px-4 pb-4 pt-1 text-xs leading-relaxed text-fg-muted">{q.data.note} Compariranno qui per agente e periodo quando il Runtime esporrà l'endpoint usage.</p>
      ) : q.isError ? (
        <p className="px-4 pb-4 pt-1 text-xs text-down">Lettura non riuscita: {q.error.message}</p>
      ) : (
        <div className="overflow-x-auto px-1.5 pb-2">
          <table className="tile-table w-full min-w-[520px] border-separate border-spacing-0 text-xs">
            <thead>
              <tr className="text-left text-2xs text-fg-subtle">
                <th className="h-8 px-2.5 font-normal">Agente</th>
                <th className="h-8 w-[28%] px-2.5 font-normal">Quota del costo</th>
                <th className="h-8 px-2.5 text-right font-normal">Chiamate</th>
                <th className="h-8 px-2.5 text-right font-normal">Token in</th>
                <th className="h-8 px-2.5 text-right font-normal">Token out</th>
                <th className="h-8 px-2.5 text-right font-normal">Costo</th>
              </tr>
            </thead>
            <tbody aria-busy={q.isPending}>
              {names.map((name) => {
                const r = byAgent.get(name);
                return <UsageLine key={name} name={name} r={r} share={r && total.cost > 0 ? r.cost / total.cost : 0} max={max} total={total.cost} pending={q.isPending} />;
              })}
              {tickerRows.length > 0 && (
                <UsageLine
                  name="ticker:*"
                  color="var(--author-ticker)"
                  r={tickerSum}
                  share={total.cost > 0 ? tickerSum.cost / total.cost : 0}
                  max={max}
                  total={total.cost}
                  pending={q.isPending}
                  label={
                    <button type="button" aria-expanded={openTickers} onClick={() => setOpenTickers((o) => !o)} className="flex items-center gap-2 rounded-item text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
                      {openTickers ? <ChevronDown className="size-3.5 text-fg-subtle" /> : <ChevronRight className="size-3.5 text-fg-subtle" />}
                      <span className="text-fg">Agenti del ticker</span>
                      <span className="num rounded-tag bg-hover px-1 text-[10px] leading-4 text-fg-subtle">{tickerRows.length}</span>
                    </button>
                  }
                />
              )}
              {openTickers &&
                tickerRows.map((r) => (
                  <UsageLine
                    key={r.agent}
                    name={r.agent}
                    nested
                    r={r}
                    share={total.cost > 0 ? r.cost / total.cost : 0}
                    max={max}
                    total={total.cost}
                    pending={false}
                    label={
                      <Link to={`/ufficio/${r.agent}`} className="flex items-center gap-2 text-fg hover:underline">
                        <AuthorChip actor={r.agent} size="xs" />
                        {tickerOf(r.agent)}
                      </Link>
                    }
                  />
                ))}
            </tbody>
            {!q.isPending && rows.length > 0 && (
              <tfoot>
                <tr className="text-fg">
                  <td className="h-9 px-2.5 font-medium">Totale</td>
                  <td />
                  <td className="num h-9 px-2.5 text-right text-fg-muted">{total.calls}</td>
                  <td className="num h-9 px-2.5 text-right text-fg-muted">{fmtTokens(total.tin)}</td>
                  <td className="num h-9 px-2.5 text-right text-fg-muted">{fmtTokens(total.tout)}</td>
                  <td className="num h-9 px-2.5 text-right font-medium">{fmtCost(total.cost)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </section>
  );
}

function MobileRow({ a, today, now, usageKnown }: { a: OfficeAgent; today: UsageTotals | null; now: number; usageKnown: boolean }) {
  const who = author(a.name);
  const last = parseTs(a.last_activity_ts);
  return (
    <li>
      <Link to={`/ufficio/${a.name}`} className="flex min-h-[60px] items-center gap-3 rounded-item px-2.5 py-2.5 transition-colors active:bg-hover">
        <AuthorChip author={who} size="md" />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-[13px] font-semibold text-fg">{who.name}</span>
            {a.status && <StatusMark agent={a.name} status={a.status} compact />}
          </span>
          <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs text-fg-subtle">
            {a.current?.ticker && <TickerTag ticker={a.current.ticker} className="h-4 px-1 text-[10px]" />}
            <span className="truncate">{a.current ? (a.current.label ?? (a.current.kind === "cycle" ? "Ciclo aperto" : "Task in corso")) : a.status ? (a.status === "idle" ? "Inattivo" : "Nessun task") : (ROLE[a.name] ?? "Agente")}</span>
          </span>
        </span>
        <span className="shrink-0 text-right">
          <span className="num block text-xs text-fg">{usageKnown ? fmtCost(today?.cost ?? 0) : last ? `${fmtAge(last, now)} fa` : "—"}</span>
          <span className="num block text-2xs text-fg-subtle">{usageKnown ? `${fmtTokens(totalTokens(today) ?? 0)} token` : "ultima attività"}</span>
        </span>
        <ChevronRight className="size-4 shrink-0 text-fg-subtle" aria-hidden />
      </Link>
    </li>
  );
}

export function Overview() {
  const q = useOfficeAgents();
  const usage = useUsage(null, "today");
  const todayOf = useTodayUsage();
  const now = useNow(15_000);
  const wide = useMediaQuery("(min-width: 768px)");
  const xl = useMediaQuery("(min-width: 1280px)");
  const recent = useRecentMessages(40);
  const { list: pending } = usePendingProposals();
  const [focus, setFocus] = useState<Focus>(NO_FOCUS);
  const saidBy = new Map<string, RecentMessage>();
  for (const m of recent.data ?? []) if (!saidBy.has(m.author)) saidBy.set(m.author, m);

  useEffect(() => {
    document.title = "Ufficio";
  }, []);

  const all = q.data && q.data.source !== "unavailable" ? q.data.data : null;
  const core = (all ?? []).filter((a) => a.kind === "core");
  const pm = core.find((a) => a.name === "portfolio_manager");
  const specialists = core.filter((a) => a.name !== "portfolio_manager").sort(canonical);
  const tickerAgents = (all ?? []).filter((a) => a.kind === "ticker");
  const pendingTickers = useMemo(() => new Set(pending.map((p) => p.ticker)), [pending]);

  const usageKnown = usage.data?.source === "runtime" || (all ?? []).some((a) => a.today !== null);
  const counts = { working: 0, waiting: 0, idle: 0 };
  for (const a of core) if (a.status) counts[a.status] += 1;
  const tickerWorking = tickerAgents.filter((a) => a.status === "working").length;
  const statusKnown = core.some((a) => a.status !== null);
  const totals = (all ?? []).reduce(
    (acc, a) => {
      const t = todayOf(a);
      return t ? { cost: acc.cost + t.cost, tokens: acc.tokens + t.tokens_in + t.tokens_out } : acc;
    },
    { cost: 0, tokens: 0 },
  );
  const stopped = statusKnown && counts.working === 0 && counts.waiting === 0 && tickerWorking === 0;

  const summary = (
    <p className="num flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-muted">
      {q.isPending ? (
        <span className="h-3 w-56 animate-pulse rounded-tag bg-hover" />
      ) : statusKnown ? (
        <>
          <span>
            <span className="font-medium text-fg">{counts.working}</span> al lavoro
          </span>
          <span>
            <span className="font-medium text-fg">{counts.waiting}</span> in attesa
          </span>
          <span>
            <span className="font-medium text-fg">{counts.idle}</span> inattivi
          </span>
        </>
      ) : (
        <span>{core.length} agenti</span>
      )}
      {tickerAgents.length > 0 && (
        <>
          <span className="text-fg-faint" aria-hidden>
            ·
          </span>
          <span>
            <span className="font-medium text-fg">{tickerAgents.length}</span> ticker, <span className="font-medium text-fg">{tickerWorking}</span> in analisi
          </span>
        </>
      )}
      {pending.length > 0 && (
        <span className="text-warn">
          <span className="font-medium">{pending.length}</span> in attesa del PM
        </span>
      )}
      {usageKnown && (
        <>
          <span className="text-fg-faint" aria-hidden>
            ·
          </span>
          <span>
            Oggi <span className="font-medium text-fg">{fmtCost(totals.cost)}</span>
          </span>
          <span>
            <span className="font-medium text-fg">{fmtTokens(totals.tokens)}</span> token
          </span>
        </>
      )}
    </p>
  );

  const header = (
    <div className="flex shrink-0 flex-wrap items-end gap-x-4 gap-y-2 px-2 pb-3 pt-1 md:px-1">
      <div className="min-w-0">
        <h1 className="text-base font-semibold tracking-[-0.01em] text-fg">Ufficio</h1>
        <div className="mt-1">{summary}</div>
      </div>
      <div className="ml-auto">
        <AssignTask />
      </div>
    </div>
  );

  const errorTile = q.isError ? (
    <div className="rounded-tile bg-ground p-6 text-sm text-fg-muted">
      <p className="text-down">Non riesco a leggere gli agenti dal Runtime.</p>
      <p className="mt-1 text-xs text-fg-subtle">{q.error.message}</p>
    </div>
  ) : null;

  const stoppedNote = stopped ? (
    <p className="mb-2.5 rounded-control bg-ground px-4 py-3 text-xs text-fg-muted">
      <span className="font-medium text-fg">L'ufficio è fermo:</span> nessun agente sta lavorando. Ripartirà al prossimo trigger dello scheduler, oppure assegna tu un task.
    </p>
  ) : null;

  const desk = (mobile: boolean, className?: string) => (
    <TickerDesk agents={all} pendingTickers={pendingTickers} usageKnown={usageKnown} focus={focus} onFocus={setFocus} mobile={mobile} className={className} />
  );

  if (!wide) {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto pb-2">
        {header}
        <div className="space-y-2.5 px-2">
          {stoppedNote}
          {errorTile ?? (
            <>
              <PmSeat a={pm} today={pm ? todayOf(pm) : null} now={now} usageKnown={usageKnown} said={saidBy.get("portfolio_manager")} focus={focus} onFocus={setFocus} />
              {desk(true)}
              <section aria-label="Specialist" className="rounded-tile bg-ground">
                <h2 className="flex h-11 items-center px-4 text-[13px] font-semibold text-fg">Specialist</h2>
                <ul data-region="seats" className="px-1.5 pb-1.5" aria-busy={q.isPending}>
                  {q.isPending
                    ? [0, 1, 2, 3, 4].map((i) => (
                        <li key={i} className="flex items-center gap-3 px-2.5 py-3">
                          <span className="size-7 animate-pulse rounded-full bg-hover" />
                          <span className="h-3 flex-1 animate-pulse rounded-tag bg-hover" />
                        </li>
                      ))
                    : specialists.map((a) => <MobileRow key={a.name} a={a} today={todayOf(a)} now={now} usageKnown={usageKnown} />)}
                </ul>
              </section>
            </>
          )}
          <SourceNote sourced={q.data} className="px-2.5" />
          <RecentActivity className="max-h-[60vh]" />
          <UsageTile order={core.map((a) => a.name)} />
        </div>
      </div>
    );
  }

  const pmColumn = <PmSeat a={pm} today={pm ? todayOf(pm) : null} now={now} usageKnown={usageKnown} said={saidBy.get("portfolio_manager")} focus={focus} onFocus={setFocus} className="min-h-[320px] flex-1" />;
  const specialistsTile = <SpecialistsTile list={specialists} todayOf={todayOf} now={now} usageKnown={usageKnown} focus={focus} onFocus={setFocus} />;

  return (
    <div data-region="workspace" className="flex min-h-0 min-w-0 flex-1 flex-col pb-2.5 pr-2.5">
      {header}
      {stoppedNote}
      {errorTile ?? (
        <div className="flex min-h-0 flex-1 gap-2.5">
          {/* Reading order is the agent graph: the PM and its queue, the ticker agents reporting to it, the specialists they call on. */}
          <div data-region="pm" className="flex w-[320px] shrink-0 flex-col gap-2.5 overflow-y-auto">
            {pmColumn}
            {!xl && specialistsTile}
          </div>
          <div data-region="desk" className="flex min-h-0 min-w-0 flex-1 flex-col gap-2.5 overflow-y-auto">
            {desk(false, "shrink-0")}
            <SourceNote sourced={q.data} className="px-1" />
            <UsageTile order={core.map((a) => a.name)} className="shrink-0" />
            {!xl && <RecentActivity className="max-h-[480px] shrink-0" />}
          </div>
          {xl && (
            <div data-region="specialists" className="flex w-[300px] shrink-0 flex-col gap-2.5 overflow-y-auto">
              {specialistsTile}
              <RecentActivity className="min-h-[240px] flex-1" />
            </div>
          )}
        </div>
      )}
      {q.isPending && <span className="sr-only">Caricamento degli agenti</span>}
    </div>
  );
}
