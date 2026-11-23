import { FileText, Plus, Trash2, X, PanelLeftClose } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type CSSProperties } from "react";
import { AuthorChip } from "@/components/author-chip";
import { IconButton, TileHeader } from "@/components/tile";
import { PANEL_SHORTCUT } from "@/shell/shell-state";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { author } from "@/lib/authors";
import { fmtAge, fmtPct, fmtPrice, parseTs } from "@/lib/format";
import { useCommand, useWatchBars, useWatchlist } from "@/lib/runtime/hooks";
import { useNow } from "@/lib/runtime/provider";
import type { Bar, WatchlistItem } from "@/lib/runtime/types";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";

type Quote = { last: number; change: number; pct: number; closes: number[] } | null;

/** Last price and change against the previous session close, from the same bars the agents read. */
function quoteFrom(bars: Bar[] | undefined): Quote {
  if (!bars || bars.length < 2) return null;
  const last = bars[bars.length - 1];
  const day = (t: number) => new Date(t * 1000).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  const lastDay = day(last.time);
  let prevClose = bars[0].close;
  for (let i = bars.length - 1; i >= 0; i--) {
    if (day(bars[i].time) !== lastDay) {
      prevClose = bars[i].close;
      break;
    }
  }
  return { last: last.close, change: last.close - prevClose, pct: ((last.close - prevClose) / prevClose) * 100, closes: bars.slice(-35).map((b) => b.close) };
}

function Spark({ closes, up }: { closes: number[]; up: boolean }) {
  if (closes.length < 2) return <span className="h-5 w-14" />;
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;
  const pts = closes.map((c, i) => `${((i / (closes.length - 1)) * 56).toFixed(1)},${(18 - ((c - min) / span) * 16 - 1).toFixed(1)}`).join(" ");
  return (
    <svg viewBox="0 0 56 18" className="h-[18px] w-14 shrink-0" aria-hidden>
      <polyline points={pts} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth="1.25" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function PriceCell({ value }: { value: number }) {
  const prev = useRef(value);
  const [flash, setFlash] = useState<"up" | "down" | null>(null);
  useEffect(() => {
    if (value !== prev.current) {
      setFlash(value > prev.current ? "up" : "down");
      prev.current = value;
      const t = setTimeout(() => setFlash(null), 900);
      return () => clearTimeout(t);
    }
  }, [value]);
  return <span className={cn("num rounded-tag px-0.5 text-sm font-medium text-fg", flash === "up" && "flash-up", flash === "down" && "flash-down")}>{fmtPrice(value)}</span>;
}

function AddTicker({ existing, compact }: { existing: string[]; compact?: boolean }) {
  const { writable } = useShell();
  const [open, setOpen] = useState(false);
  const [ticker, setTicker] = useState("");
  const [note, setNote] = useState("");
  const add = useCommand("add_watchlist", { invalidate: [["watchlist"]] });
  const symbol = ticker.trim().toUpperCase();
  const dup = existing.includes(symbol);
  const valid = /^[A-Z][A-Z0-9.\-]{0,9}$/.test(symbol) && !dup;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    add.mutate(
      { ticker: symbol, note: note.trim() || null },
      {
        onSuccess: () => {
          setTicker("");
          setNote("");
          setOpen(false);
        },
      },
    );
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant={compact ? "ghost" : "outline"} size="sm" disabled={!writable} aria-label="Aggiungi un ticker alla watchlist" className={compact ? "size-7 px-0" : ""}>
          <Plus className="size-4" />
          {!compact && "Aggiungi ticker"}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 border-line-strong bg-raised p-3">
        <form onSubmit={submit} className="space-y-2.5">
          <div>
            <label htmlFor="wl-ticker" className="text-xs text-fg-muted">
              Ticker
            </label>
            <input
              id="wl-ticker"
              autoFocus
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="es. AMZN"
              autoComplete="off"
              className="mt-1 h-8 w-full rounded-control border border-line-strong bg-ground px-2.5 text-sm uppercase text-fg outline-none placeholder:normal-case placeholder:text-fg-subtle focus:border-accent-c"
            />
            {dup && <p className="mt-1 text-xs text-warn">{symbol} è già in watchlist.</p>}
          </div>
          <div>
            <label htmlFor="wl-note" className="text-xs text-fg-muted">
              Nota per gli agenti <span className="text-fg-subtle">(facoltativa)</span>
            </label>
            <textarea
              id="wl-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="Perché seguirlo"
              className="mt-1 w-full resize-none rounded-control border border-line-strong bg-ground px-2.5 py-1.5 text-sm text-fg outline-none placeholder:text-fg-subtle focus:border-accent-c"
            />
          </div>
          <p className="text-2xs leading-relaxed text-fg-subtle">Stesso comando degli agenti (add_watchlist): il ticker comparirà a tuo nome e lo vedranno al prossimo ciclo.</p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>
              Annulla
            </Button>
            <Button type="submit" size="sm" disabled={!valid || add.isPending}>
              Aggiungi
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}

function RemoveButton({ item, onDone }: { item: WatchlistItem; onDone?: () => void }) {
  const { writable } = useShell();
  const [open, setOpen] = useState(false);
  const remove = useCommand("remove_watchlist", { invalidate: [["watchlist"]] });
  const a = author(item.added_by);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={!writable}
          onClick={(e) => e.stopPropagation()}
          aria-label={`Togli ${item.ticker} dalla watchlist`}
          className="grid size-6 place-items-center rounded-item text-fg-subtle opacity-0 transition-opacity hover:bg-hover hover:text-down focus-visible:opacity-100 group-hover:opacity-100 group-data-[active=true]:opacity-100 disabled:hidden"
        >
          <X className="size-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 border-line-strong bg-raised p-3 text-xs" onClick={(e) => e.stopPropagation()}>
        <p className="text-sm text-fg">Togliere {item.ticker} dalla watchlist?</p>
        <p className="mt-1 leading-relaxed text-fg-muted">
          {a.kind === "human" ? "L'hai aggiunto tu." : `L'ha aggiunto ${a.name}.`} Gli agenti smettono di seguirlo dal prossimo ciclo.
        </p>
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            Annulla
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(
                { ticker: item.ticker },
                {
                  onSuccess: () => {
                    setOpen(false);
                    onDone?.();
                  },
                },
              )
            }
          >
            <Trash2 className="size-3.5" /> Togli
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export function Watchlist({
  selected,
  onSelect,
  onHide,
  className,
  style,
}: {
  selected: string | null;
  onSelect: (t: string) => void;
  onHide?: () => void;
  className?: string;
  style?: CSSProperties;
}) {
  const wl = useWatchlist();
  const items = useMemo(() => wl.data ?? [], [wl.data]);
  const bars = useWatchBars(items.map((i) => i.ticker));
  const now = useNow(30_000);
  const listRef = useRef<HTMLUListElement>(null);

  const onKeyDown = (e: KeyboardEvent<HTMLUListElement>) => {
    if (!items.length) return;
    const idx = Math.max(0, items.findIndex((i) => i.ticker === selected));
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = items[(idx + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length];
      onSelect(next.ticker);
      requestAnimationFrame(() => listRef.current?.querySelector<HTMLElement>(`[data-ticker="${next.ticker}"]`)?.focus());
    }
  };

  return (
    <section data-region="watchlist" aria-label="Watchlist condivisa" className={cn("flex min-h-0 flex-col bg-ground", className)} style={style}>
      <TileHeader title="Watchlist" meta={wl.data ? String(items.length) : undefined} hint="Condivisa con gli agenti: è l\u2019universo che analizzano">
        <AddTicker existing={items.map((i) => i.ticker)} compact />
        {onHide && <IconButton icon={PanelLeftClose} label="Nascondi la watchlist" shortcut={PANEL_SHORTCUT.left} onClick={onHide} />}
      </TileHeader>

      {wl.isPending ? (
        <ul className="px-1.5" aria-busy>
          {Array.from({ length: 6 }).map((_, i) => (
            <li key={i} className="flex items-center gap-3 rounded-item px-2.5 py-3">
              <div className="h-3.5 w-12 animate-pulse rounded-item bg-hover" />
              <div className="ml-auto h-3.5 w-16 animate-pulse rounded-item bg-hover" />
            </li>
          ))}
        </ul>
      ) : wl.isError ? (
        <div className="p-4 text-xs leading-relaxed">
          <p className="text-down">Watchlist non disponibile.</p>
          <p className="mt-1 text-fg-subtle">{wl.error.message}</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={() => wl.refetch()}>
            Riprova
          </Button>
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-1 flex-col items-start gap-3 p-4">
          <p className="text-sm text-fg">La watchlist è vuota.</p>
          <p className="text-xs leading-relaxed text-fg-muted">
            È la lista che seguono gli agenti: aggiungi un ticker e il Technical Analyst lo analizzerà al prossimo ciclo. Anche gli agenti possono aggiungerne, a loro nome.
          </p>
          <AddTicker existing={[]} />
        </div>
      ) : (
        <ul ref={listRef} role="listbox" aria-label="Ticker" onKeyDown={onKeyDown} className="min-h-0 flex-1 space-y-px overflow-y-auto px-1.5 pb-1.5">
          {items.map((item, i) => {
            const q = quoteFrom(bars[i]?.data);
            const loading = bars[i]?.isPending;
            const active = item.ticker === selected;
            const a = author(item.added_by);
            const up = (q?.change ?? 0) >= 0;
            return (
              <li
                key={item.ticker}
                data-ticker={item.ticker}
                data-active={active}
                role="option"
                data-part="row"
                aria-selected={active}
                tabIndex={active || (!selected && i === 0) ? 0 : -1}
                onClick={() => onSelect(item.ticker)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(item.ticker);
                  }
                }}
                className={cn(
                  "group cursor-pointer rounded-item px-2.5 py-2 outline-none transition-colors duration-150 focus-visible:bg-hover",
                  active ? "bg-selected shadow-[inset_0_0_0_1px_oklch(1_0_0/0.05)]" : "hover:bg-hover",
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="w-12 shrink-0 text-[13px] font-semibold tracking-[-0.005em] text-fg">{item.ticker}</span>
                  {q ? <Spark closes={q.closes} up={up} /> : <span className="h-[18px] w-14" />}
                  <span className="ml-auto flex flex-col items-end leading-tight">
                    {q ? (
                      <>
                        <PriceCell value={q.last} />
                        <span className={cn("num text-2xs", up ? "text-up" : "text-down")}>{fmtPct(q.pct)}</span>
                      </>
                    ) : loading ? (
                      <span className="h-3.5 w-14 animate-pulse rounded-item bg-hover" />
                    ) : (
                      <span className="text-2xs text-fg-subtle">Nessun dato</span>
                    )}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-2xs text-fg-subtle">
                  <AuthorChip author={a} size="xs" tooltip={`Aggiunto da ${a.name}${a.kind === "human" && a.channel ? ` via ${a.channel}` : ""}`} />
                  <span className="min-w-0 flex-1 truncate" title={item.note ?? undefined}>
                    {item.note || <span className="italic text-fg-subtle">nessuna nota</span>}
                  </span>
                  <span className="num shrink-0" title={new Date(parseTs(item.added_ts) ?? 0).toLocaleString("it-IT")}>
                    {fmtAge(parseTs(item.added_ts), now)}
                  </span>
                  <Link
                    to={`/ticker/${item.ticker}`}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                    aria-label={`Scheda di ${item.ticker}`}
                    title={`Scheda di ${item.ticker}`}
                    className="grid size-6 place-items-center rounded-item text-fg-subtle opacity-0 outline-none transition-opacity hover:bg-hover hover:text-fg focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring/60 group-hover:opacity-100 group-data-[active=true]:opacity-100"
                  >
                    <FileText className="size-3.5" strokeWidth={1.75} />
                  </Link>
                  <RemoveButton item={item} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
