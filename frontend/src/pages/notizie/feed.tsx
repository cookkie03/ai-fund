import { useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Bookmark, Loader2, SearchX, WalletCards } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useNewsFeed, useNewsHead } from "@/features/news/hooks";
import { dayKey, dayLabel, fmtClock, providerLabel } from "@/features/news/labels";
import type { NewsFilters, NewsItem } from "@/features/news/types";
import { useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { Notice, ReadError, TickerTag, UsageMarks } from "./parts";

export type FeedState = ReturnType<typeof useFeed>;

/** The feed and its live head. New items never enter the list on their own: they wait behind "N nuove". */
export function useFeed(filters: NewsFilters) {
  const qc = useQueryClient();
  const { target } = useRuntime();
  const feed = useNewsFeed(filters);
  const first = feed.data?.pages[0];
  const items = useMemo(() => feed.data?.pages.flatMap((p) => (p.state === "ok" ? p.data.items : [])) ?? [], [feed.data]);
  const unavailable = first?.state === "unavailable" ? first.endpoint : null;
  const head = useNewsHead(filters, first?.state === "ok");
  const fresh = useMemo(() => {
    if (head.data?.state !== "ok" || !feed.data) return [];
    const known = new Set(items.map((i) => i.id));
    const top = items[0] ? Date.parse(items[0].published_ts) : 0;
    return head.data.data.items.filter((i) => !known.has(i.id) && Date.parse(i.published_ts) >= top);
  }, [head.data, items, feed.data]);
  const [arrived, setArrived] = useState<Set<number>>(new Set());

  const reveal = () => {
    setArrived(new Set(fresh.map((i) => i.id)));
    qc.resetQueries({ queryKey: ["news_feed", target.id] });
  };
  return { feed, items, unavailable, fresh, arrived, reveal };
}

function Row({ item, selected, arrived, onSelect }: { item: NewsItem; selected: boolean; arrived: boolean; onSelect: (id: number) => void }) {
  return (
    <li className={cn(arrived && "row-arrive")}>
      <button
        type="button"
        data-news={item.id}
        aria-current={selected ? "true" : undefined}
        onClick={() => onSelect(item.id)}
        className={cn(
          "group grid w-full grid-cols-[42px_minmax(0,1fr)] gap-x-2 rounded-item px-2 py-2 text-left outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring/60",
          selected ? "bg-selected shadow-[inset_0_0.5px_0_oklch(1_0_0/0.06)]" : "hover:bg-hover",
        )}
      >
        <time dateTime={item.published_ts} className="num pt-px text-xs text-fg-subtle">
          {fmtClock(item.published_ts)}
        </time>
        <span className="min-w-0">
          <span className={cn("line-clamp-2 text-[13px] font-medium leading-[1.15rem]", selected ? "text-fg" : "text-fg group-hover:text-fg")}>{item.headline}</span>
          <span className="mt-1 flex min-w-0 items-center gap-1.5 text-2xs text-fg-subtle">
            <span className="min-w-0 truncate">
              {item.source} <span className="text-fg-faint">·</span> {providerLabel(item.provider)}
            </span>
            {(item.in_portfolio || item.in_watchlist) && (
              <span className="inline-flex shrink-0 items-center text-fg-muted" role="img" aria-label={item.in_portfolio ? "Riguarda il portafoglio" : "Riguarda la watchlist"} title={item.in_portfolio ? "Riguarda il portafoglio" : "Riguarda la watchlist"}>
                {item.in_portfolio ? <WalletCards className="size-3" strokeWidth={2} /> : <Bookmark className="size-3" strokeWidth={2} />}
              </span>
            )}
            {item.tickers.length > 0 && (
              <span className="flex shrink-0 items-center gap-1">
                {item.tickers.slice(0, 3).map((t) => (
                  <TickerTag key={t} symbol={t} strong={item.in_portfolio || item.in_watchlist} />
                ))}
                {item.tickers.length > 3 && <span className="num text-[10px]">+{item.tickers.length - 3}</span>}
              </span>
            )}
            <UsageMarks usage={item.usage} className="ml-auto pl-2" />
          </span>
        </span>
      </button>
    </li>
  );
}

/** The wire: day sections, newest first, infinite. ↑/↓ or j/k move the selection. */
export function FeedList({ state, selected, onSelect, filtersActive, onClear, header }: { state: FeedState; selected: number | null; onSelect: (id: number) => void; filtersActive: boolean; onClear: () => void; header?: ReactNode }) {
  const { feed, items, unavailable, fresh, arrived, reveal } = state;
  const scroller = useRef<HTMLDivElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && feed.hasNextPage && !feed.isFetchingNextPage) feed.fetchNextPage();
    }, { root: scroller.current, rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, [feed, items.length]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowDown" || e.key === "j" ? 1 : e.key === "ArrowUp" || e.key === "k" ? -1 : 0;
    if (!step || !items.length || (e.target as HTMLElement).closest("input,textarea")) return;
    e.preventDefault();
    const i = items.findIndex((x) => x.id === selected);
    const next = items[Math.max(0, Math.min(items.length - 1, i === -1 ? 0 : i + step))];
    onSelect(next.id);
    scroller.current?.querySelector<HTMLButtonElement>(`[data-news="${next.id}"]`)?.focus({ preventScroll: false });
  };

  const showNew = () => {
    scroller.current?.scrollTo({ top: 0 });
    reveal();
  };

  let body: ReactNode;
  if (feed.isPending)
    body = (
      <ul aria-busy aria-label="Caricamento delle notizie" className="space-y-1 px-1.5 py-1">
        {Array.from({ length: 9 }, (_, i) => (
          <li key={i} className="grid grid-cols-[42px_1fr] gap-x-2 px-2 py-2">
            <span className="h-3 w-8 animate-pulse rounded-tag bg-hover" />
            <span className="space-y-1.5">
              <span className="block h-3 animate-pulse rounded-tag bg-hover" style={{ width: `${88 - (i % 4) * 11}%` }} />
              <span className="block h-2.5 w-32 animate-pulse rounded-tag bg-hover" />
            </span>
          </li>
        ))}
      </ul>
    );
  else if (feed.isError) body = <ReadError error={feed.error} what="le notizie" />;
  else if (unavailable)
    body = (
      <Notice
        title="Il Runtime non espone ancora le notizie"
        detail={
          <>
            Il flusso comparirà quando il Runtime esporrà <code className="text-fg">{unavailable}</code>. Gli agenti leggono le notizie con i loro tool anche senza questa pagina.
          </>
        }
      />
    );
  else if (!items.length)
    body = filtersActive ? (
      <Notice icon={<SearchX />} title="Nessuna notizia per questi filtri" detail="Allarga l'ambito o togli un filtro: l'archivio è lo stesso che leggono gli agenti.">
        <Button variant="outline" size="sm" onClick={onClear}>
          Togli i filtri
        </Button>
      </Notice>
    ) : (
      <Notice title="L'archivio è ancora vuoto" detail="Le notizie arrivano dalle fonti attive a ogni ciclo di ingestione. Controlla lo stato delle fonti se resta vuoto." />
    );
  else {
    let lastDay = "";
    body = (
      <ul aria-label="Notizie" className="px-1.5 pb-2">
        {items.map((it) => {
          const k = dayKey(it.published_ts);
          const head = k !== lastDay;
          lastDay = k;
          return (
            <Fragment key={it.id}>
              {head && (
                <li aria-hidden className="sticky top-0 z-[1] -mx-1.5 bg-ground px-3.5 pb-1 pt-2.5 text-2xs font-medium text-fg-subtle">
                  {dayLabel(it.published_ts)}
                </li>
              )}
              <Row item={it} selected={it.id === selected} arrived={arrived.has(it.id)} onSelect={onSelect} />
            </Fragment>
          );
        })}
      </ul>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {header}
      <div className="relative flex min-h-0 flex-1 flex-col">
      {fresh.length > 0 && (
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center" data-part="fresh">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={showNew}
                className="row-arrive pointer-events-auto mt-2 inline-flex h-7 items-center gap-1.5 rounded-control bg-raised px-3 text-xs font-medium text-fg shadow-[0_6px_20px_oklch(0_0_0/0.45),inset_0_0.5px_0_oklch(1_0_0/0.08)] outline-none transition-colors hover:bg-selected focus-visible:ring-2 focus-visible:ring-ring/60"
              >
                <ArrowUp className="size-3.5" /> {fresh.length === 1 ? "1 nuova notizia" : `${fresh.length >= 50 ? "50+" : fresh.length} nuove notizie`}
              </button>
            </TooltipTrigger>
            <TooltipContent>Le mostro in cima; quello che stai leggendo resta dov'è</TooltipContent>
          </Tooltip>
        </div>
      )}
      <div ref={scroller} onKeyDown={onKeyDown} className="min-h-0 flex-1 overflow-y-auto">
        {body}
        <div ref={sentinel} aria-hidden className="h-px" />
        {feed.isFetchingNextPage && (
          <p className="flex items-center justify-center gap-2 py-3 text-2xs text-fg-subtle">
            <Loader2 className="size-3.5 animate-spin" /> Carico le notizie precedenti
          </p>
        )}
        {!feed.hasNextPage && items.length > 20 && <p className="py-4 text-center text-2xs text-fg-subtle">Fine dell'archivio per questi filtri</p>}
      </div>
      </div>
    </div>
  );
}
