import { ChevronLeft, Rss } from "lucide-react";
import { forwardRef, useEffect, useState, type ComponentProps } from "react";
import { Gutter } from "@/components/gutter";
import { PanelTab, PanelTabContent, PanelTabs, PanelTabsList } from "@/components/panel-tabs";
import { useCalendar, useNewsFilters, useNewsLive, useNewsSources } from "@/features/news/hooks";
import { fmtAge, parseTs } from "@/lib/format";
import { useNow } from "@/lib/runtime/provider";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { useFreshness } from "@/shell/status";
import { CalendarPanel } from "./calendar";
import { FeedList, useFeed, type FeedState } from "./feed";
import { DesktopFilters, MobileFilters, SearchField, useFilterOptions } from "./filters";
import { NewsReader } from "./reader";
import { SourcesSheet } from "./sources";

const READER_KEY = "cockpit.notizie.reader";
const READER = { min: 420, max: 860, initial: 580 };

function loadWidth(): number {
  try {
    const n = Number(localStorage.getItem(READER_KEY));
    if (n >= READER.min && n <= READER.max) return n;
  } catch {
    /* storage unavailable */
  }
  return READER.initial;
}

const SourcesButton = forwardRef<HTMLButtonElement, ComponentProps<"button"> & { problems: number; compact?: boolean }>(({ problems, compact, className, ...props }, ref) => (
  <button
    ref={ref}
    type="button"
    aria-label={`Fonti${problems ? `, ${problems} con problemi` : ""}`}
    className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-control text-xs font-medium text-fg-muted outline-none transition-colors hover:bg-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-ring/60", compact ? "h-9 bg-ground px-3" : "h-7 px-2.5", className)}
    {...props}
  >
    <Rss className="size-3.5" strokeWidth={1.75} /> Fonti
    {problems > 0 && <span className="num rounded-tag bg-warn-soft px-1 text-[10px] leading-4 text-warn">{problems}</span>}
  </button>
));
SourcesButton.displayName = "SourcesButton";

/** Live state and the age of the newest item: the wire always says how current it is. */
function Freshness({ feed }: { feed: FeedState }) {
  const { state } = useFreshness();
  const now = useNow(30_000);
  const newest = feed.fresh[0]?.published_ts ?? feed.items[0]?.published_ts;
  return (
    <span className="inline-flex items-center gap-x-3">
      <span className={cn("inline-flex items-center gap-1.5", state === "down" ? "text-down" : state === "stale" ? "text-warn" : "text-fg-subtle")}>
        <span className={cn("size-1.5 rounded-full", state === "live" ? "bg-up" : state === "down" ? "bg-down" : state === "stale" ? "bg-warn" : "bg-fg-faint")} aria-hidden />
        {state === "live" ? "Dal vivo" : state === "down" ? "Runtime irraggiungibile" : state === "stale" ? "Stream fermo" : "Connessione…"}
      </span>
      {newest && (
        <span>
          Ultima notizia{" "}
          {fmtAge(parseTs(newest), now) === "ora" ? (
            <span className="text-fg-muted">adesso</span>
          ) : (
            <>
              <span className="num text-fg-muted">{fmtAge(parseTs(newest), now)}</span> fa
            </>
          )}
        </span>
      )}
    </span>
  );
}

const SampleTag = () =>
  import.meta.env.VITE_NEWS_FIXTURES === "1" ? (
    <span data-sample className="rounded-tag bg-warn-soft px-1.5 py-px font-medium text-warn" title="COCKPIT_NEWS_FIXTURES=1: notizie sintetiche del dev server, non l'archivio del Runtime">
      Dati di esempio
    </span>
  ) : null;

/** Count of today's and tomorrow's events that touch the portfolio or watchlist, for the Calendario tab. */
function useCalendarBadge(): number {
  const q = useCalendar(7);
  if (q.data?.state !== "ok") return 0;
  const limit = Date.now() + 48 * 3600_000;
  return q.data.data.filter((e) => (e.in_portfolio || e.in_watchlist) && Date.parse(e.ts) >= Date.now() && Date.parse(e.ts) < limit).length;
}

/**
 * Notizie: the agents' own news environment, open to Luca as a colleague. A wire that shows who used each
 * item, a reader with the usage trace and Inoltra, the macro and earnings calendar, and the sources.
 */
export function NotiziePage() {
  const desktop = useMediaQuery("(min-width: 1024px)");
  const ctl = useNewsFilters();
  const feed = useFeed(ctl.filters);
  const sources = useNewsSources();
  const opts = useFilterOptions(feed.items, sources.data?.state === "ok" ? sources.data.data : null);
  useNewsLive();

  useEffect(() => {
    document.title = "Notizie";
  }, []);

  // On the desk the reader always shows something: the newest item until Luca picks one.
  const firstId = feed.items[0]?.id ?? null;
  useEffect(() => {
    if (desktop && ctl.selected === null && firstId !== null) ctl.select(firstId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desktop, firstId, ctl.selected]);

  return desktop ? <Desktop ctl={ctl} feed={feed} opts={opts} /> : <Phone ctl={ctl} feed={feed} opts={opts} />;
}

type Props = { ctl: ReturnType<typeof useNewsFilters>; feed: FeedState; opts: ReturnType<typeof useFilterOptions> };

function Desktop({ ctl, feed, opts }: Props) {
  const [width, setWidth] = useState(loadWidth);
  const [tab, setTab] = useState("news");
  const badge = useCalendarBadge();
  const resize = (px: number) => {
    const w = Math.round(Math.min(READER.max, Math.max(READER.min, px)));
    setWidth(w);
    try {
      localStorage.setItem(READER_KEY, String(w));
    } catch {
      /* storage unavailable */
    }
  };

  return (
    <div data-region="workspace" className="flex min-h-0 min-w-0 flex-1 flex-col pb-2.5 pr-2.5">
      <div className="flex shrink-0 items-end gap-4 px-1 pb-3 pt-1">
        <div className="min-w-0">
          <h1 className="text-base font-semibold tracking-[-0.01em] text-fg">Notizie</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-fg-subtle">
            <span>Lo stesso archivio che leggono gli agenti</span>
            <SampleTag />
            <Freshness feed={feed} />
          </p>
        </div>
        <div className="ml-auto">
          <SourcesSheet trigger={(n) => <SourcesButton problems={n} />} />
        </div>
      </div>
      <div className="flex min-h-0 flex-1">
        <section aria-label="Flusso delle notizie" className="tile-enter-left flex min-w-[460px] flex-1 flex-col overflow-hidden rounded-tile bg-ground">
          <header className="flex h-11 shrink-0 items-center gap-2 pl-4 pr-2.5">
            <h2 className="text-[13px] font-semibold tracking-[-0.005em] text-fg">Flusso</h2>
            {feed.items.length > 0 && (
              <span className="num rounded-tag bg-hover px-1.5 text-[10px] leading-4 text-fg-subtle">
                {feed.items.length}
                {feed.feed.hasNextPage ? "+" : ""}
              </span>
            )}
            <SearchField value={ctl.filters.q} onChange={(v) => ctl.setFilter("q", v)} className="ml-auto w-64" />
          </header>
          <DesktopFilters ctl={ctl} opts={opts} />
          <FeedList state={feed} selected={ctl.selected} onSelect={(id) => (ctl.select(id), setTab("news"))} filtersActive={ctl.active > 0} onClear={ctl.clearFilters} />
        </section>
        <Gutter orientation="vertical" label="Larghezza del lettore" value={width} min={READER.min} max={READER.max} direction={-1} onResize={resize} onReset={() => resize(READER.initial)} />
        <section aria-label="Lettore" className="tile-enter-right flex shrink-0 flex-col overflow-hidden rounded-tile bg-ground" style={{ width }}>
          <PanelTabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
            <PanelTabsList>
              <PanelTab value="news">Notizia</PanelTab>
              <PanelTab value="calendar" count={badge}>
                Calendario
              </PanelTab>
            </PanelTabsList>
            <PanelTabContent value="news" className="tab-in flex min-h-0 flex-col">
              <NewsReader id={ctl.selected} />
            </PanelTabContent>
            <PanelTabContent value="calendar" className="tab-in flex min-h-0 flex-col">
              <CalendarPanel />
            </PanelTabContent>
          </PanelTabs>
        </section>
      </div>
    </div>
  );
}

function Phone({ ctl, feed, opts }: Props) {
  const [tab, setTab] = useState<"feed" | "calendar">("feed");
  const badge = useCalendarBadge();

  if (ctl.selected !== null)
    return (
      <div data-region="workspace" className="flex min-h-0 min-w-0 flex-1 flex-col">
        <h1 className="sr-only">Notizie</h1>
        <div className="flex shrink-0 items-center gap-1 px-2 pb-2 pt-1">
          <button
            type="button"
            onClick={() => (window.history.state?.idx > 0 ? window.history.back() : ctl.select(null))}
            className="inline-flex h-9 items-center gap-1 rounded-control pl-1 pr-3 text-[13px] font-medium text-fg-muted transition-colors hover:bg-hover hover:text-fg"
          >
            <ChevronLeft className="size-5" /> Notizie
          </button>
        </div>
        <div className="mx-2 mb-2 flex min-h-0 flex-1 flex-col overflow-hidden rounded-tile bg-ground">
          <NewsReader id={ctl.selected} className="pt-3" />
        </div>
      </div>
    );

  return (
    <div data-region="workspace" className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center gap-2 px-2 pb-2 pt-1">
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-semibold tracking-[-0.01em] text-fg">Notizie</h1>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-2xs text-fg-subtle">
            <SampleTag />
            <Freshness feed={feed} />
          </p>
        </div>
        <SourcesSheet trigger={(n) => <SourcesButton problems={n} compact />} />
      </div>
      <div role="tablist" aria-label="Sezioni delle notizie" className="mx-2 mb-2 flex h-9 shrink-0 gap-0.5 rounded-control bg-ground p-0.5">
        {(["feed", "calendar"] as const).map((id) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn("flex flex-1 items-center justify-center gap-1.5 rounded-item text-xs font-medium transition-colors duration-150", tab === id ? "bg-hover text-fg" : "text-fg-subtle hover:text-fg")}
          >
            {id === "feed" ? "Flusso" : "Calendario"}
            {id === "calendar" && badge > 0 && <span className="num rounded-tag bg-hover px-1 text-[10px] leading-4 text-fg-muted">{badge}</span>}
          </button>
        ))}
      </div>
      {tab === "feed" ? (
        <>
          <div className="flex shrink-0 gap-2 px-2 pb-2">
            <SearchField value={ctl.filters.q} onChange={(v) => ctl.setFilter("q", v)} className="h-9 min-w-0 flex-1 bg-ground" />
            <MobileFilters ctl={ctl} opts={opts} />
          </div>
          <section aria-label="Flusso delle notizie" className="mx-2 mb-2 flex min-h-0 flex-1 flex-col overflow-hidden rounded-tile bg-ground">
            <FeedList state={feed} selected={null} onSelect={(id) => ctl.select(id, { push: true })} filtersActive={ctl.active > 0} onClear={ctl.clearFilters} />
          </section>
        </>
      ) : (
        <section aria-label="Calendario" className="mx-2 mb-2 flex min-h-0 flex-1 flex-col overflow-hidden rounded-tile bg-ground pt-2">
          <CalendarPanel />
        </section>
      )}
    </div>
  );
}
