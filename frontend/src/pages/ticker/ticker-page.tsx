import { CandlestickChart, MessagesSquare, OctagonPause, RotateCw, WalletCards } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { useDossier, useDossierHistory } from "@/features/dossier/hooks";
import { DOSSIER_STATUS, fmtFraction } from "@/features/dossier/labels";
import type { Dossier } from "@/features/dossier/types";
import { useOfficeAgents } from "@/features/office/hooks";
import type { OfficeAgent } from "@/features/office/types";
import { author, tickerAgentId } from "@/lib/authors";
import { fmtDateTime, fmtMoney, fmtPrice, fmtQty, fmtVolume, fmtWhen } from "@/lib/format";
import { useNow } from "@/lib/runtime/provider";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { AssignTask } from "../ufficio/assign-task";
import { StatusMark, STATUS_LABEL } from "../ufficio/parts";
import { AuthorFocusProvider, authorKey, useAuthorFocus } from "./author-focus";
import { DecisionsTile, DesksSection, LessonsTile, NotesTile, ProposalTile, ThesisTile, VersionsTile } from "./tiles";

/** Phone reading order: the decision first, then why, then the record. */
const SECTIONS = [
  ["proposta", "Proposta"],
  ["tesi", "Tesi"],
  ["analisi", "Analisi"],
  ["note", "Note"],
  ["decisioni", "Decisioni"],
  ["lezioni", "Lezioni"],
  ["versioni", "Versioni"],
] as const;

const SYMBOL = /^[A-Z0-9.\-^=]{1,12}$/;

/** /ticker/:symbol — the ticker's dossier: what the office knows and thinks about it, every fact signed. */
export function TickerPage() {
  const { symbol: raw = "" } = useParams();
  const symbol = raw.toUpperCase();
  if (!SYMBOL.test(symbol)) return <Navigate to="/ufficio" replace />;
  if (raw !== symbol) return <Navigate to={`/ticker/${symbol}`} replace />;
  return (
    <AuthorFocusProvider key={symbol}>
      <Dossierpage symbol={symbol} />
    </AuthorFocusProvider>
  );
}

function useTickerAgent(symbol: string): { agent: OfficeAgent | null; known: boolean } {
  const q = useOfficeAgents();
  return useMemo(() => {
    const d = q.data;
    if (!d || d.source === "unavailable") return { agent: null, known: false };
    return { agent: d.data.find((a) => a.name === tickerAgentId(symbol)) ?? null, known: true };
  }, [q.data, symbol]);
}

function Dossierpage({ symbol }: { symbol: string }) {
  const q = useDossier(symbol);
  const history = useDossierHistory(symbol);
  const ta = useTickerAgent(symbol);
  // Without the ticker-agent backend an absent `ticker:<SYM>` row says nothing: only claim "no agent" once the dossier read exists.
  const backend = q.data?.state === "ok" || q.data?.state === "missing";
  const agent = ta.agent;
  const known = ta.known && backend;
  const mobile = useMediaQuery("(max-width: 767px)");
  const scroller = useRef<HTMLDivElement>(null);
  const d = q.data?.state === "ok" ? q.data.data : null;

  useEffect(() => {
    document.title = `${symbol} · Scheda`;
  }, [symbol]);

  let body: ReactNode;
  if (q.isPending) body = <Skeleton />;
  else if (q.isError)
    body = (
      <Notice title={`Non riesco a leggere la scheda di ${symbol}`} detail={q.error.message}>
        <Button size="sm" variant="secondary" onClick={() => q.refetch()}>
          <RotateCw className="size-3.5" /> Riprova
        </Button>
      </Notice>
    );
  else if (q.data.state === "unavailable")
    body = (
      <Notice title="La scheda del ticker non è ancora esposta dal Runtime" detail={`Comparirà quando il Runtime esporrà ${q.data.endpoint}. Grafico e chat dell'agente restano raggiungibili dai link qui sopra.`} />
    );
  else if (q.data.state === "missing")
    body = (
      <Notice title={`Nessuna scheda per ${symbol}`} detail={agent ? `L'agente di ${symbol} la apre al suo primo ciclo.` : `Non c'è ancora un agente del ticker per ${symbol}: è il PM a crearlo quando decide di seguire il titolo.`}>
        <AssignTask
          agent="portfolio_manager"
          ticker={symbol}
          align="start"
          trigger={
            <Button size="sm" variant="secondary">
              Chiedi al PM di seguire {symbol}
            </Button>
          }
        />
      </Notice>
    );
  else body = <Mosaic d={q.data.data} history={history.data} mobile={mobile} />;

  return (
    <div ref={scroller} data-region="dossier" className="min-h-0 min-w-0 flex-1 overflow-y-auto pb-2.5 md:pr-2.5">
      <Header symbol={symbol} d={d} agent={agent} agentKnown={known} mobile={mobile} />
      {d && mobile && <SectionIndex root={scroller} />}
      <div className="px-2 md:px-0">{body}</div>
    </div>
  );
}

// ——— Header ———

function Header({ symbol, d, agent, agentKnown, mobile }: { symbol: string; d: Dossier | null; agent: OfficeAgent | null; agentKnown: boolean; mobile: boolean }) {
  const now = useNow(60_000);
  const { halted } = useShell();
  const id = d?.identity;
  const p = d?.portfolio;
  const agentId = tickerAgentId(symbol);
  const links = (
    <nav aria-label={`Collegamenti per ${symbol}`} className="flex flex-wrap gap-1">
      <HeaderLink to={`/terminale?t=${symbol}`} icon={<CandlestickChart />} label="Grafico" />
      {(agent || !agentKnown) && <HeaderLink to={`/ufficio/${agentId}`} icon={<MessagesSquare />} label="Chat dell'agente" />}
      <HeaderLink to="/portafoglio" icon={<WalletCards />} label="Portafoglio" />
    </nav>
  );

  return (
    <header className="mx-2 mb-2.5 rounded-tile bg-ground px-4 py-3.5 md:mx-0 md:px-5 md:py-4">
      <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
        <div className="min-w-0">
          <Breadcrumb className="mb-2">
            <BreadcrumbList className="text-2xs">
              <BreadcrumbItem>
                <BreadcrumbLink render={<Link to="/terminale">Terminale</Link>} />
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{symbol}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <div className="flex items-center gap-2 text-[13px] text-fg-muted">
            <h1 className="font-semibold tracking-[0.02em] text-fg">{symbol}</h1>
            {id?.name && <span className="truncate">{id.name}</span>}
          </div>
          {id && <p className="mt-1 flex items-baseline gap-2.5">
            <span className={cn("num font-semibold tracking-[-0.02em] text-fg", mobile ? "text-2xl" : "text-[30px] leading-9")}>{id?.current_price != null ? `$${fmtPrice(id.current_price)}` : "—"}</span>
            {id?.as_of && (
              <time className="num text-2xs text-fg-subtle" dateTime={id.as_of} title={fmtDateTime(id.as_of)}>
                {fmtWhen(id.as_of, now)}
              </time>
            )}
          </p>}
          {(id?.sector || id?.industry || id?.market_cap != null) && (
            <p className="mt-1 text-xs text-fg-subtle">
              {[id?.sector, id?.industry].filter(Boolean).join(" · ")}
              {id?.market_cap != null && <span className="num"> · cap. ${fmtVolume(id.market_cap)}</span>}
            </p>
          )}
        </div>

        {d && (
          <dl className="grid min-w-0 grid-cols-[auto_auto] gap-x-4 gap-y-2 text-xs sm:grid-cols-[auto_auto_auto_auto] md:grid-cols-[auto_auto]">
            <dt className="text-fg-subtle">Scheda</dt>
            <dd className="flex items-center gap-2">
              <span className="font-medium text-fg">{DOSSIER_STATUS[d.status] ?? d.status}</span>
              <span className="num text-fg-subtle">v{d.version}</span>
            </dd>
            <dt className="text-fg-subtle">Aggiornata</dt>
            <dd className="flex min-w-0 items-center gap-1.5 text-fg-muted">
              {d.updated_by && <AuthorChip actor={d.updated_by} size="xs" />}
              <span className="truncate">{d.updated_by ? author(d.updated_by).short : "—"}</span>
              {d.updated_ts && (
                <time className="num shrink-0 text-fg-subtle" dateTime={d.updated_ts} title={fmtDateTime(d.updated_ts)}>
                  · {fmtWhen(d.updated_ts, now)}
                </time>
              )}
            </dd>
            {d.stale_count > 0 && (
              <>
                <dt className="text-fg-subtle">Fatti vecchi</dt>
                <dd>
                  <a href="#analisi" className="num rounded-tag bg-warn-soft px-1.5 leading-5 text-warn outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
                    {d.stale_count} da rivedere
                  </a>
                </dd>
              </>
            )}
          </dl>
        )}

        <div className="min-w-0 text-xs">
          <p className="text-fg-subtle">Agente del ticker</p>
          {agent ? (
            <Link to={`/ufficio/${agentId}`} className="mt-1 flex items-center gap-2 rounded-item outline-none hover:text-fg focus-visible:ring-2 focus-visible:ring-ring/60">
              <AuthorChip actor={agentId} size="sm" />
              <span className="font-medium text-fg">{author(agentId).name}</span>
              <StatusMark agent={agentId} status={agent.status} compact />
              <span className="text-fg-muted">{agent.status ? STATUS_LABEL[agent.status] : "Stato non esposto"}</span>
            </Link>
          ) : agentKnown ? (
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="text-fg-muted">Nessun agente: il PM non segue ancora {symbol}</span>
              {d && (
                <AssignTask
                  agent="portfolio_manager"
                  ticker={symbol}
                  align="start"
                  trigger={
                    <Button size="xs" variant="ghost">
                      Chiedi al PM
                    </Button>
                  }
                />
              )}
            </div>
          ) : (
            <p className="mt-1 text-fg-subtle">Stato non esposto da GET /v1/read/agents</p>
          )}
        </div>

        {p?.invested && (
          <div className="min-w-0 text-xs">
            <p className="text-fg-subtle">Posizione</p>
            <p className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="num font-medium text-fg">{fmtQty(p.qty)} az.</span>
              <span className="num text-fg-muted">a ${fmtPrice(p.avg_entry_price)}</span>
              <span className="num text-fg-muted">{fmtFraction(p.position_weight)} del portafoglio</span>
              {p.unrealized_pnl != null && <span className={cn("num font-medium", p.unrealized_pnl > 0 ? "text-up" : p.unrealized_pnl < 0 ? "text-down" : "text-fg")}>{fmtMoney(p.unrealized_pnl, { sign: true })}</span>}
            </p>
            {(p.sector_exposure != null || p.cash_fraction != null) && (
              <p className="num mt-1 text-2xs text-fg-subtle">
                Settore {fmtFraction(p.sector_exposure)} · cassa {fmtFraction(p.cash_fraction)}
              </p>
            )}
          </div>
        )}

        <div className="ml-auto flex flex-col items-end gap-2 max-md:ml-0 max-md:w-full max-md:items-start">{links}</div>
      </div>

      {halted && (
        <p role="status" className="mt-3 flex items-center gap-2 rounded-item bg-halt-ground px-2.5 py-1.5 text-xs text-fg">
          <OctagonPause className="size-3.5 shrink-0 text-halt" strokeWidth={2} aria-hidden />
          Trading in Halt: puoi leggere e annotare la scheda, ma nessuna proposta può essere accettata.
        </p>
      )}
      {d && !mobile && <AuthorLegend d={d} />}
    </header>
  );
}

function HeaderLink({ to, icon, label }: { to: string; icon: ReactNode; label: string }) {
  return (
    <Link
      to={to}
      className="inline-flex h-7 items-center gap-1.5 rounded-control bg-raised px-2.5 text-xs text-fg-muted outline-none transition-colors hover:bg-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-ring/60 [&_svg]:size-3.5 [&_svg]:stroke-[1.75]"
    >
      {icon}
      {label}
    </Link>
  );
}

/** Who signed what: one toggle per author; hovering or pinning lights their facts across the mosaic. */
function AuthorLegend({ d }: { d: Dossier }) {
  const { pinned, togglePin, setHover } = useAuthorFocus();
  const authors = useMemo(() => {
    const ids = [d.thesis?.author, ...d.desks.map((f) => f.agent), ...d.decisions.map((x) => x.actor), ...d.notes.map((n) => n.author)].filter((a): a is string => !!a);
    const seen = new Map<string, string>();
    for (const a of ids) if (!seen.has(authorKey(a))) seen.set(authorKey(a), a);
    return Array.from(seen.entries());
  }, [d]);
  if (authors.length < 2) return null;
  return (
    <div className="-mx-2 mt-3 flex flex-wrap items-center gap-1" role="group" aria-label="Evidenzia i fatti di un autore">
      <span className="ml-2 mr-1 text-2xs text-fg-subtle">Firme</span>
      {authors.map(([key, actor]) => {
        const on = pinned === key;
        return (
          <button
            key={key}
            type="button"
            aria-pressed={on}
            onClick={() => togglePin(key)}
            onMouseEnter={() => setHover(key)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(key)}
            onBlur={() => setHover(null)}
            className={cn("inline-flex h-7 items-center gap-1.5 rounded-control px-2 text-xs outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/60", on ? "bg-selected text-fg" : "text-fg-muted hover:bg-hover hover:text-fg")}
          >
            <AuthorChip actor={actor} size="xs" />
            {author(actor).short}
          </button>
        );
      })}
    </div>
  );
}

// ——— Mosaic ———

function Mosaic({ d, history, mobile }: { d: Dossier; history: Parameters<typeof VersionsTile>[0]["history"]; mobile: boolean }) {
  if (mobile)
    return (
      <div className="space-y-2">
        <ProposalTile d={d} />
        <ThesisTile d={d} />
        <DesksSection d={d} />
        <NotesTile d={d} />
        <DecisionsTile d={d} />
        <LessonsTile d={d} />
        <VersionsTile d={d} history={history} />
      </div>
    );
  return (
    <div className="grid grid-cols-12 gap-2.5">
      <ThesisTile d={d} className="col-span-12 lg:col-span-7" />
      <ProposalTile d={d} className="col-span-12 lg:col-span-5" />
      <div className="col-span-12">
        <DesksSection d={d} />
      </div>
      <DecisionsTile d={d} className="col-span-12 lg:col-span-7" />
      <LessonsTile d={d} className="col-span-12 lg:col-span-5" />
      <NotesTile d={d} className="col-span-12 lg:col-span-7" />
      <VersionsTile d={d} history={history} className="col-span-12 lg:col-span-5" />
    </div>
  );
}

/** Phone: a sticky index of the sections, the current one marked as you scroll. */
function SectionIndex({ root }: { root: React.RefObject<HTMLDivElement | null> }) {
  const [current, setCurrent] = useState<string>("proposta");
  const bar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const els = SECTIONS.map(([id]) => document.getElementById(id)).filter((e): e is HTMLElement => !!e);
    const io = new IntersectionObserver(
      (entries) => {
        const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (top) setCurrent(top.target.id);
      },
      { root: root.current, rootMargin: "-56px 0px -60% 0px" },
    );
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [root]);
  useEffect(() => {
    bar.current?.querySelector<HTMLElement>(`[data-id="${current}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [current]);
  return (
    <div ref={bar} className="sticky top-0 z-10 mb-2 flex gap-1 overflow-x-auto bg-desk px-2 py-1.5 [scrollbar-width:none]">
      <nav aria-label="Sezioni della scheda" className="flex gap-1">
        {SECTIONS.map(([id, label]) => (
          <a
            key={id}
            data-id={id}
            href={`#${id}`}
            aria-current={current === id ? "location" : undefined}
            className={cn("inline-flex h-8 shrink-0 items-center rounded-control px-3 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/60", current === id ? "bg-selected font-medium text-fg" : "text-fg-muted")}
          >
            {label}
          </a>
        ))}
      </nav>
    </div>
  );
}

function Notice({ title, detail, children }: { title: string; detail?: string; children?: ReactNode }) {
  return (
    <div className="rounded-tile bg-ground px-5 py-6">
      <p className="text-sm font-medium text-fg">{title}</p>
      {detail && <p className="mt-1 max-w-[70ch] text-xs leading-relaxed text-fg-muted">{detail}</p>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}

function Skeleton() {
  const block = (h: string, span: string) => (
    <div className={cn("rounded-tile bg-ground p-4", span)}>
      <span className="block h-3 w-24 animate-pulse rounded-tag bg-hover" />
      <span className={cn("mt-4 block animate-pulse rounded-item bg-hover/60", h)} />
    </div>
  );
  return (
    <div className="grid grid-cols-12 gap-2.5" aria-busy aria-label="Caricamento della scheda">
      {block("h-40", "col-span-12 lg:col-span-7")}
      {block("h-40", "col-span-12 lg:col-span-5")}
      {block("h-24", "col-span-12")}
    </div>
  );
}
