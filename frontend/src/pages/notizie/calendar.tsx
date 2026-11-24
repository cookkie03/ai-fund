import { Bookmark, CalendarX2, WalletCards } from "lucide-react";
import { Fragment, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useCalendar } from "@/features/news/hooks";
import { dayKey, dayLabel, fmtClock, IMPORTANCE_LABEL, IMPORTANCE_LEVEL } from "@/features/news/labels";
import type { CalendarEvent } from "@/features/news/types";
import { useNow } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { Notice, ReadError } from "./parts";

type Kind = "all" | "macro" | "earnings";
const KIND_LABEL: Record<Kind, string> = { all: "Tutti", macro: "Macro", earnings: "Trimestrali" };

/** Importance as three 3 px bars, filled up to the level; always paired with a label for assistive tech. */
function ImportanceBars({ value }: { value: CalendarEvent["importance"] }) {
  const level = value ? IMPORTANCE_LEVEL[value] : 0;
  return (
    <span role="img" aria-label={value ? `Importanza ${IMPORTANCE_LABEL[value].toLowerCase()}` : "Importanza non indicata"} title={value ? `Importanza ${IMPORTANCE_LABEL[value].toLowerCase()}` : "Importanza non indicata"} className="inline-flex h-3 items-end gap-[2px]">
      {[1, 2, 3].map((i) => (
        <span key={i} className={cn("w-[3px]", i <= level ? (level === 3 ? "bg-fg" : "bg-fg-muted") : "bg-line-strong")} style={{ height: 4 + i * 2.5 }} />
      ))}
    </span>
  );
}

function Figure({ label, value, strong }: { label: string; value: string | null; strong?: boolean }) {
  return (
    <span className="flex min-w-0 flex-col items-start @md:items-end">
      <span className="text-[10px] leading-3 text-fg-subtle">{label}</span>
      <span className={cn("num text-xs", value ? (strong ? "font-semibold text-fg" : "text-fg-muted") : "text-fg-faint")}>{value ?? "—"}</span>
    </span>
  );
}

function EventRow({ e, past }: { e: CalendarEvent; past: boolean }) {
  const mine = e.in_portfolio || e.in_watchlist;
  return (
    <li
      data-mine={mine || undefined}
      className={cn("grid grid-cols-[40px_14px_minmax(0,1fr)] items-center gap-x-2 gap-y-1 rounded-item px-2 py-2 @md:grid-cols-[40px_14px_minmax(0,1fr)_auto]", mine && "bg-[oklch(0.25_0.014_258/0.7)]", past && "opacity-60")}
    >
      <time dateTime={e.ts} className="num text-xs text-fg-subtle">
        {fmtClock(e.ts)}
      </time>
      <ImportanceBars value={e.importance} />
      <span className="min-w-0">
        <span className="flex min-w-0 items-center gap-1.5">
          {e.ticker && (
            <Link to={`/ticker/${e.ticker}`} className={cn("num inline-flex h-4 shrink-0 items-center rounded-tag px-1 text-[10px] font-semibold tracking-[0.02em] outline-none hover:bg-line-strong focus-visible:ring-2 focus-visible:ring-ring/60", mine ? "bg-selected text-fg" : "bg-hover text-fg-muted")}>
              {e.ticker}
            </Link>
          )}
          <span className={cn("truncate text-[13px] leading-5", e.importance === "high" ? "font-medium text-fg" : "text-fg")}>{e.title}</span>
        </span>
        <span className="flex items-center gap-1.5 text-2xs text-fg-subtle">
          {e.kind === "earnings" ? "Trimestrale" : "Macro"}
          {e.country && <> · {e.country}</>}
          {mine && (
            <span className="inline-flex items-center gap-1 text-fg-muted">
              · {e.in_portfolio ? <WalletCards className="size-3" aria-hidden /> : <Bookmark className="size-3" aria-hidden />}
              {e.in_portfolio ? "in portafoglio" : "in watchlist"}
            </span>
          )}
        </span>
      </span>
      <span className="col-start-3 grid w-fit grid-cols-3 gap-x-4 @md:col-start-auto @md:w-auto @md:gap-x-3">
        <Figure label="Attuale" value={e.actual} strong />
        <Figure label="Atteso" value={e.forecast} />
        <Figure label="Prec." value={e.previous} />
      </span>
    </li>
  );
}

/** Macro and earnings for today and the next seven days; holdings and watchlist names stand out. */
export function CalendarPanel({ header }: { header?: (controls: ReactNode) => ReactNode }) {
  const q = useCalendar(7);
  const now = useNow(60_000);
  const [kind, setKind] = useState<Kind>("all");

  const controls = (
    <div role="radiogroup" aria-label="Tipo di evento" className="seg">
      {(Object.keys(KIND_LABEL) as Kind[]).map((k) => (
        <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)} className="seg-item">
          {KIND_LABEL[k]}
        </button>
      ))}
    </div>
  );

  let body: ReactNode;
  if (q.isPending)
    body = (
      <ul aria-busy aria-label="Caricamento del calendario" className="space-y-1 px-3 py-2">
        {Array.from({ length: 7 }, (_, i) => (
          <li key={i} className="h-9 animate-pulse rounded-item bg-hover/60" />
        ))}
      </ul>
    );
  else if (q.isError) body = <ReadError error={q.error} what="il calendario" />;
  else if (q.data.state === "unavailable")
    body = (
      <Notice
        title="Il calendario non è ancora esposto dal Runtime"
        detail={
          <>
            Macro e trimestrali compariranno quando il Runtime esporrà <code className="text-fg">{q.data.endpoint}</code>.
          </>
        }
      />
    );
  else {
    const all = q.data.state === "ok" ? q.data.data : [];
    const list = all.filter((e) => kind === "all" || e.kind === kind);
    if (!list.length)
      body = (
        <Notice
          icon={<CalendarX2 />}
          title={all.length ? `Nessun evento ${kind === "macro" ? "macro" : "di trimestrali"} nei prossimi 7 giorni` : "Nessun evento nei prossimi 7 giorni"}
          detail="Il calendario arriva da OpenBB: se la fonte non è disponibile resta vuoto. Controlla lo stato nelle Fonti."
        />
      );
    else {
      let last = "";
      body = (
        <ul aria-label="Eventi in calendario" className="@container px-1.5 pb-3">
          {list.map((e) => {
            const k = dayKey(e.ts);
            const head = k !== last;
            last = k;
            return (
              <Fragment key={e.id}>
                {head && (
                  <li aria-hidden className="sticky top-0 z-[1] -mx-1.5 bg-ground px-3.5 pb-1 pt-2.5 text-2xs font-medium text-fg-subtle">
                    {dayLabel(e.ts, now)}
                  </li>
                )}
                <EventRow e={e} past={Date.parse(e.ts) < now} />
              </Fragment>
            );
          })}
        </ul>
      );
    }
  }

  return (
    <div data-part="calendar" className="flex min-h-0 flex-1 flex-col">
      {header ? header(controls) : <div className="flex shrink-0 items-center gap-2 px-2.5 pb-2">{controls}</div>}
      <div className="min-h-0 flex-1 overflow-y-auto">{body}</div>
    </div>
  );
}
