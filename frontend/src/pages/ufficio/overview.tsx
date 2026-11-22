import { ArrowUpRight, ChevronRight, ListPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { Button } from "@/components/ui/button";
import { PERIOD_LABEL, useOfficeAgents, useRecentMessages, useUsage, type RecentMessage, type UsagePeriod } from "@/features/office/hooks";
import type { OfficeAgent, UsageTotals } from "@/features/office/types";
import { author } from "@/lib/authors";
import { fmtAge, fmtWhen, parseTs } from "@/lib/format";
import { useNow } from "@/lib/runtime/provider";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { AssignTask } from "./assign-task";
import { fmtCost, fmtTokens, Meter, ROLE, SourceNote, StatusMark, TickerTag, totalTokens, onRadioKeys } from "./parts";

const ORDER: Record<string, number> = { working: 0, waiting: 1, idle: 2 };

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
      <span className="min-w-0 truncate text-fg-muted">
        {c.label ?? `${kind}${c.id !== null ? ` #${c.id}` : ""} aperto`}
      </span>
    </span>
  );
}

/** One seat of the office: who, what they are on, how recently they acted, what they cost today. */
function Seat({ a, today, now, usageKnown, said }: { a: OfficeAgent; today: UsageTotals | null; now: number; usageKnown: boolean; said?: RecentMessage }) {
  const who = author(a.name);
  const last = parseTs(a.last_activity_ts);
  return (
    <article className="group relative flex min-w-0 flex-col rounded-tile bg-ground p-4 transition-colors duration-150 hover:bg-[oklch(0.2_0.008_260)]">
      <div className="flex items-start gap-3">
        <AuthorChip author={who} size="lg" tooltip={`${who.name}${a.model ? ` · ${a.model}` : ""}`} />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[13px] font-semibold text-fg">
            <Link to={`/ufficio/${a.name}`} className="outline-none after:absolute after:inset-0 after:rounded-tile focus-visible:after:ring-2 focus-visible:after:ring-ring/70">
              {who.name}
            </Link>
          </h3>
          <p className="truncate text-2xs text-fg-subtle">{a.role ?? ROLE[a.name] ?? "Agente"}</p>
        </div>
        {a.status && <StatusMark agent={a.name} status={a.status} />}
      </div>

      <div className="mt-3.5 flex h-6 min-w-0 items-center text-xs">{workLine(a)}</div>

      <p className="mt-2 line-clamp-2 min-h-8 text-xs leading-4 text-fg-subtle">
        {said ? (
          <>
            <span className="text-fg-muted">«{said.text}»</span> <span className="num whitespace-nowrap">in {said.ticker}</span>
          </>
        ) : (
          "Nessun messaggio nei cicli recenti."
        )}
      </p>

      <dl className="mt-3 grid grid-cols-3 gap-3">
        <Meter label="Ultima attività" value={last ? `${fmtAge(last, now)} fa` : "—"} hint={last ? fmtWhen(a.last_activity_ts, now) : "Nessuna attività registrata"} />
        {usageKnown && (
          <>
            <Meter label="Costo oggi" value={fmtCost(today?.cost ?? 0)} />
            <Meter label="Token oggi" value={fmtTokens(totalTokens(today) ?? 0)} hint={today ? `${fmtTokens(today.tokens_in)} in · ${fmtTokens(today.tokens_out)} out · ${today.calls} chiamate` : undefined} />
          </>
        )}
      </dl>

      <div className="relative z-10 mt-3 flex items-center gap-1 opacity-100 transition-opacity duration-150 lg:opacity-0 lg:group-focus-within:opacity-100 lg:group-hover:opacity-100">
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
        <span className="ml-auto inline-flex items-center gap-1 text-2xs text-fg-subtle">
          Apri chat e tool <ArrowUpRight className="size-3" aria-hidden />
        </span>
      </div>
    </article>
  );
}

function SeatSkeleton() {
  return (
    <div className="rounded-tile bg-ground p-4" aria-hidden>
      <div className="flex items-center gap-3">
        <span className="size-9 animate-pulse rounded-full bg-hover" />
        <span className="flex-1 space-y-1.5">
          <span className="block h-3 w-32 animate-pulse rounded-tag bg-hover" />
          <span className="block h-2.5 w-24 animate-pulse rounded-tag bg-hover" />
        </span>
      </div>
      <span className="mt-4 block h-5 w-40 animate-pulse rounded-tag bg-hover" />
      <span className="mt-4 block h-8 animate-pulse rounded-item bg-hover" />
    </div>
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

/** Cost and tokens per agent for a period: the office's running bill, read from the Runtime's LLM calls. */
function UsageTile({ order, className }: { order: string[]; className?: string }) {
  const [period, setPeriod] = useState<UsagePeriod>("today");
  const q = useUsage(null, period);
  const rows = q.data?.source === "runtime" ? q.data.data : [];
  const byAgent = new Map(rows.map((r) => [r.agent, r]));
  const names = [...order, ...rows.map((r) => r.agent).filter((n) => !order.includes(n))];
  const total = rows.reduce((acc, r) => ({ cost: acc.cost + r.cost, tin: acc.tin + r.tokens_in, tout: acc.tout + r.tokens_out, calls: acc.calls + r.calls }), { cost: 0, tin: 0, tout: 0, calls: 0 });
  const max = Math.max(0, ...rows.map((r) => r.cost));
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
                const who = author(name);
                const share = r && total.cost > 0 ? r.cost / total.cost : 0;
                return (
                  <tr key={name} className="hover:[&>td]:bg-hover">
                    <td className="h-8 px-2.5 transition-colors">
                      <span className="flex items-center gap-2">
                        <AuthorChip author={who} size="xs" />
                        <span className="truncate text-fg">{who.name}</span>
                      </span>
                    </td>
                    <td className="h-8 px-2.5 transition-colors">
                      {q.isPending ? (
                        <span className="block h-1.5 w-full animate-pulse rounded-tag bg-hover" />
                      ) : (
                        <span className="flex items-center gap-2">
                          <span className="relative h-1.5 flex-1 overflow-hidden rounded-tag bg-[oklch(0_0_0/0.3)]">
                            <span className="absolute inset-y-0 left-0 rounded-tag" style={{ width: `${max > 0 && r ? (r.cost / max) * 100 : 0}%`, backgroundColor: who.color }} />
                          </span>
                          <span className="num w-9 text-right text-2xs text-fg-subtle">{Math.round(share * 100)}%</span>
                        </span>
                      )}
                    </td>
                    <td className="num h-8 px-2.5 text-right text-fg-muted transition-colors">{q.isPending ? "…" : (r?.calls ?? 0)}</td>
                    <td className="num h-8 px-2.5 text-right text-fg-muted transition-colors">{q.isPending ? "…" : fmtTokens(r?.tokens_in ?? 0)}</td>
                    <td className="num h-8 px-2.5 text-right text-fg-muted transition-colors">{q.isPending ? "…" : fmtTokens(r?.tokens_out ?? 0)}</td>
                    <td className="num h-8 px-2.5 text-right text-fg transition-colors">{q.isPending ? "…" : fmtCost(r?.cost ?? 0)}</td>
                  </tr>
                );
              })}
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
      <Link to={`/ufficio/${a.name}`} className="flex min-h-[64px] items-center gap-3 rounded-item px-2.5 py-2.5 transition-colors active:bg-hover">
        <AuthorChip author={who} size="md" />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-[13px] font-semibold text-fg">{who.name}</span>
            {a.status && <StatusMark agent={a.name} status={a.status} compact />}
          </span>
          <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs text-fg-subtle">
            {a.current?.ticker && <TickerTag ticker={a.current.ticker} className="h-4 px-1 text-[10px]" />}
            <span className="truncate">{a.current ? (a.current.label ?? (a.current.kind === "cycle" ? "Ciclo aperto" : "Task in corso")) : a.status ? (a.status === "idle" ? "Inattivo" : "Nessun task") : (a.role ?? ROLE[a.name])}</span>
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
  const recent = useRecentMessages(40);
  const saidBy = new Map<string, RecentMessage>();
  for (const m of recent.data ?? []) if (!saidBy.has(m.author)) saidBy.set(m.author, m);

  useEffect(() => {
    document.title = "Ufficio";
  }, []);

  const agents = q.data && q.data.source !== "unavailable" ? [...q.data.data].sort((x, y) => (ORDER[x.status ?? ""] ?? 3) - (ORDER[y.status ?? ""] ?? 3)) : [];
  const usageKnown = usage.data?.source === "runtime" || agents.some((a) => a.today !== null);
  const counts = { working: 0, waiting: 0, idle: 0 };
  for (const a of agents) if (a.status) counts[a.status] += 1;
  const statusKnown = agents.some((a) => a.status !== null);
  const totals = agents.reduce(
    (acc, a) => {
      const t = todayOf(a);
      return t ? { cost: acc.cost + t.cost, tokens: acc.tokens + t.tokens_in + t.tokens_out } : acc;
    },
    { cost: 0, tokens: 0 },
  );
  const stopped = statusKnown && counts.working === 0 && counts.waiting === 0;

  const summary = (
    <p className="num flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-muted">
      {q.isPending ? (
        <span className="h-3 w-56 animate-pulse rounded-tag bg-hover" />
      ) : statusKnown ? (
        <>
          <span><span className="font-medium text-fg">{counts.working}</span> al lavoro</span>
          <span><span className="font-medium text-fg">{counts.waiting}</span> in attesa</span>
          <span><span className="font-medium text-fg">{counts.idle}</span> inattivi</span>
        </>
      ) : (
        <span>{agents.length} agenti</span>
      )}
      {usageKnown && (
        <>
          <span className="text-fg-faint" aria-hidden>·</span>
          <span>Oggi <span className="font-medium text-fg">{fmtCost(totals.cost)}</span></span>
          <span><span className="font-medium text-fg">{fmtTokens(totals.tokens)}</span> token</span>
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

  const body = q.isError ? (
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

  if (!wide) {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto pb-2">
        {header}
        <div className="px-2">
          {stoppedNote}
          {body ?? (
            <ul data-region="seats" className="rounded-tile bg-ground p-1.5" aria-busy={q.isPending}>
              {q.isPending
                ? [0, 1, 2, 3, 4, 5].map((i) => (
                    <li key={i} className="flex items-center gap-3 px-2.5 py-3">
                      <span className="size-7 animate-pulse rounded-full bg-hover" />
                      <span className="h-3 flex-1 animate-pulse rounded-tag bg-hover" />
                    </li>
                  ))
                : agents.map((a) => <MobileRow key={a.name} a={a} today={todayOf(a)} now={now} usageKnown={usageKnown} />)}
            </ul>
          )}
          <SourceNote sourced={q.data} className="px-2.5 pt-2.5" />
          <RecentActivity className="mt-2.5 max-h-[60vh]" />
          <UsageTile order={agents.map((a) => a.name)} className="mt-2.5" />
        </div>
      </div>
    );
  }

  return (
    <div data-region="workspace" className="flex min-h-0 min-w-0 flex-1 gap-2.5 pb-2.5 pr-2.5">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto">
        {header}
        {stoppedNote}
        {body ?? (
          <div data-region="seats" className="grid grid-cols-[repeat(auto-fill,minmax(296px,1fr))] gap-2.5" aria-busy={q.isPending}>
            {q.isPending ? [0, 1, 2, 3, 4, 5].map((i) => <SeatSkeleton key={i} />) : agents.map((a) => <Seat key={a.name} a={a} today={todayOf(a)} now={now} usageKnown={usageKnown} said={saidBy.get(a.name)} />)}
          </div>
        )}
        <SourceNote sourced={q.data} className="px-1 pt-3" />
        <UsageTile order={agents.map((a) => a.name)} className="mt-2.5 shrink-0" />
      </div>
      <RecentActivity className="hidden w-[340px] shrink-0 lg:flex" />
    </div>
  );
}

