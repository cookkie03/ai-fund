import { ArrowUpRight, Bookmark, CandlestickChart, FileText, MessagesSquare, Newspaper, WalletCards } from "lucide-react";
import { Link } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ForwardMenu } from "@/features/news/forward";
import { useNewsItem } from "@/features/news/hooks";
import { fmtClock, fmtFull, hostOf, providerLabel, safeUrl, USAGE_VERB } from "@/features/news/labels";
import type { NewsDetail, UsageEntry } from "@/features/news/types";
import { author, LUCA } from "@/lib/authors";
import { fmtAge, parseTs } from "@/lib/format";
import { useNow } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { Notice, ReadError } from "./parts";

function chatHref(e: UsageEntry): string {
  return `/ufficio/${e.agent}${e.topic ? `?chat=${encodeURIComponent(e.topic)}` : ""}`;
}

/** One signed line of the usage trace: who, what, when, and the way into the cycle's chat. */
function UsageLine({ e, now }: { e: UsageEntry; now: number }) {
  const a = author(e.agent);
  const forwarded = e.kind === "forwarded";
  return (
    <li className="row-arrive grid grid-cols-[20px_minmax(0,1fr)_auto] items-start gap-x-2.5 py-1.5">
      <AuthorChip author={forwarded ? LUCA : a} size="sm" />
      <div className="min-w-0 text-[13px] leading-5">
        {forwarded ? (
          <p className="text-fg">
            <span className="font-medium">Luca</span> <span className="text-fg-muted">l'ha inoltrata a</span> <span className="font-medium">{a.name}</span>
          </p>
        ) : (
          <p className="text-fg">
            <span className="font-medium">{a.name}</span> <span className="text-fg-muted">{USAGE_VERB[e.kind]}</span>
          </p>
        )}
        {e.note && (
          <blockquote className="mt-1 rounded-item bg-[oklch(0.82_0.135_72/0.08)] px-2.5 py-1.5 text-xs leading-[1.1rem] text-fg-muted">
            <span className="text-[var(--author-luca)]">«</span>
            {e.note}
            <span className="text-[var(--author-luca)]">»</span>
          </blockquote>
        )}
        <Link to={chatHref(e)} className="mt-0.5 inline-flex items-center gap-1 text-2xs text-fg-subtle underline-offset-2 hover:text-fg hover:underline">
          <MessagesSquare className="size-3" aria-hidden />
          {e.cycle_id !== null ? <>Ciclo <span className="num">{e.cycle_id}</span> · </> : null}
          {e.topic === "cockpit" ? "chat con Luca" : e.topic ? `chat #${e.topic}` : "chat"}
        </Link>
      </div>
      <Tooltip>
        <TooltipTrigger asChild>
          <time dateTime={e.ts} className="num pt-0.5 text-2xs text-fg-subtle">
            {fmtAge(parseTs(e.ts), now)}
          </time>
        </TooltipTrigger>
        <TooltipContent>{fmtFull(e.ts)}</TooltipContent>
      </Tooltip>
    </li>
  );
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function UsageTrace({ n }: { n: NewsDetail }) {
  const now = useNow(30_000);
  const list = [...n.usage_detail].sort((a, b) => (parseTs(b.ts) ?? 0) - (parseTs(a.ts) ?? 0));
  const agents = new Set(list.filter((e) => e.kind !== "forwarded").map((e) => e.agent)).size;
  return (
    <section aria-labelledby="usage-title" className="mt-6">
      <h3 id="usage-title" className="text-[13px] font-semibold text-fg">Uso da parte degli agenti</h3>
      {list.length > 0 && (
        <p className="num mt-0.5 text-2xs text-fg-subtle">
          {[plural(n.usage.reads, "lettura", "letture"), plural(n.usage.citations, "citazione", "citazioni"), plural(n.usage.forwards, "inoltro", "inoltri"), agents ? plural(agents, "agente", "agenti") : null].filter(Boolean).join(" · ")}
        </p>
      )}
      {list.length === 0 ? (
        <p className="mt-1.5 max-w-[60ch] text-xs leading-[1.1rem] text-fg-muted">Nessun agente l'ha ancora letta, citata o ricevuta. Se pensi che debba pesarla qualcuno, inoltrala con il tuo parere.</p>
      ) : (
        <ul className="mt-1">{list.map((e, i) => <UsageLine key={`${e.agent}-${e.kind}-${e.ts}-${i}`} e={e} now={now} />)}</ul>
      )}
    </section>
  );
}

function TickerLinks({ n }: { n: NewsDetail }) {
  if (!n.tickers.length) return null;
  return (
    <ul aria-label="Ticker della notizia" className="mt-3 flex flex-wrap gap-1.5">
      {n.tickers.map((t) => (
        <li key={t} className="inline-flex h-7 items-stretch overflow-hidden rounded-item bg-hover text-xs">
          <Link to={`/ticker/${t}`} className="num inline-flex items-center gap-1 pl-2 pr-1.5 font-semibold tracking-[0.02em] text-fg outline-none transition-colors hover:bg-selected focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60" title={`Scheda di ${t}`}>
            <FileText className="size-3 text-fg-subtle" aria-hidden /> {t}
          </Link>
          <Link to={`/terminale?t=${t}`} aria-label={`${t} nel Terminale`} title={`${t} nel Terminale`} className="grid w-7 place-items-center border-l border-line text-fg-subtle outline-none transition-colors hover:bg-selected hover:text-fg focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60">
            <CandlestickChart className="size-3.5" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Body({ n }: { n: NewsDetail }) {
  const text = n.full_text ?? n.summary;
  const img = safeUrl(n.image_url);
  return (
    <div className="mt-5">
      {img && <img src={img} alt="" loading="lazy" className="mb-4 max-h-56 w-full rounded-item object-cover" />}
      {text ? (
        <div className="max-w-[68ch] space-y-3 text-[15px] leading-[1.6] text-fg-muted [&>p:first-child]:text-fg">
          {text.split(/\n{2,}/).map((p, i) => (
            <p key={i}>{p}</p>
          ))}
          {!n.full_text && n.summary && <p className="text-xs text-fg-subtle">La fonte fornisce solo il sommario{safeUrl(n.url) ? ": il testo completo è sull'originale." : "."}</p>}
        </div>
      ) : (
        <p className="max-w-[60ch] rounded-item bg-[oklch(0_0_0/0.18)] px-3 py-2.5 text-xs leading-[1.1rem] text-fg-muted">
          La fonte fornisce solo il titolo{safeUrl(n.url) ? ": leggi l'articolo sull'originale." : ", senza testo né link all'originale."}
        </p>
      )}
    </div>
  );
}

function Article({ n }: { n: NewsDetail }) {
  const url = safeUrl(n.url);
  return (
    <article aria-labelledby="news-title" className="mx-auto w-full max-w-[720px] px-5 pb-10 pt-2 md:px-6">
      <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-fg-subtle">
        <span className="text-fg-muted">{n.source}</span>
        <span className="text-fg-faint">·</span>
        <span>{providerLabel(n.provider)}</span>
        <span className="text-fg-faint">·</span>
        <time dateTime={n.published_ts} className="num">
          {fmtFull(n.published_ts)}
        </time>
        {(n.in_portfolio || n.in_watchlist) && (
          <span className="ml-1 inline-flex items-center gap-1 rounded-tag bg-hover px-1.5 text-2xs text-fg-muted">
            {n.in_portfolio ? <WalletCards className="size-3" /> : <Bookmark className="size-3" />}
            {n.in_portfolio ? "Portafoglio" : "Watchlist"}
          </span>
        )}
      </p>
      <h2 id="news-title" className="mt-2 text-balance text-xl font-semibold leading-[1.3] tracking-[-0.012em] text-fg md:text-[22px]">
        {n.headline}
      </h2>
      <TickerLinks n={n} />
      <div className="mt-4 flex flex-wrap items-center gap-1.5">
        <ForwardMenu item={n} />
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex h-7 items-center gap-1.5 rounded-control px-2.5 text-xs font-medium text-fg-muted outline-none transition-colors hover:bg-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-ring/60">
            Apri su {hostOf(url) ?? "l'originale"} <ArrowUpRight className="size-3.5" aria-hidden />
          </a>
        )}
        <span className="ml-auto hidden text-2xs text-fg-subtle sm:inline">
          Arrivata alle <span className="num">{fmtClock(n.fetched_ts)}</span>
        </span>
      </div>
      <Body n={n} />
      <UsageTrace n={n} />
    </article>
  );
}

/** The reader: one item set for reading, then who in the office used it. */
export function NewsReader({ id, className }: { id: number | null; className?: string }) {
  const q = useNewsItem(id);
  let body;
  if (id === null)
    body = (
      <Notice icon={<Newspaper />} title="Scegli una notizia dal flusso" detail="Qui la leggi per intero, vedi quali agenti l'hanno letta, citata o ricevuta e la inoltri con il tuo parere.">
        <span className="inline-flex items-center gap-1.5 text-2xs text-fg-subtle">
          <kbd className="rounded-tag bg-hover px-1">↑</kbd>
          <kbd className="rounded-tag bg-hover px-1">↓</kbd> per scorrere il flusso
        </span>
      </Notice>
    );
  else if (q.isPending)
    body = (
      <div aria-busy aria-label="Caricamento della notizia" className="mx-auto w-full max-w-[720px] space-y-3 px-6 pt-3">
        <span className="block h-3 w-48 animate-pulse rounded-tag bg-hover" />
        <span className="block h-6 w-11/12 animate-pulse rounded-tag bg-hover" />
        <span className="block h-6 w-2/3 animate-pulse rounded-tag bg-hover" />
        <span className="mt-6 block h-3 w-full animate-pulse rounded-tag bg-hover" />
        <span className="block h-3 w-full animate-pulse rounded-tag bg-hover" />
        <span className="block h-3 w-4/5 animate-pulse rounded-tag bg-hover" />
      </div>
    );
  else if (q.isError) body = <ReadError error={q.error} what="la notizia" />;
  else if (q.data.state === "unavailable")
    body = (
      <Notice
        title="Il dettaglio della notizia non è ancora esposto"
        detail={
          <>
            Il lettore e la traccia d'uso compariranno quando il Runtime esporrà <code className="text-fg">{q.data.endpoint}</code>.
          </>
        }
      />
    );
  else if (q.data.state === "missing") body = <Notice title="Notizia non trovata" detail="Non è più nell'archivio: la retention compatta le notizie vecchie." />;
  else body = <Article n={q.data.data} />;

  return (
    <div data-part="reader" className={cn("min-h-0 flex-1 overflow-y-auto", className)}>
      {body}
    </div>
  );
}

