import { Check, ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { PROVIDER_LABEL, SCOPE_LABEL, providerLabel } from "@/features/news/labels";
import type { NewsFilters, NewsItem, NewsScope, NewsSource } from "@/features/news/types";
import { cn } from "@/lib/utils";

export type Option = { value: string; label: string; hint?: string };

type Ctl = {
  filters: NewsFilters;
  setFilter: (key: keyof NewsFilters, value: string) => void;
  clearFilters: () => void;
  active: number;
};

/** Filter choices from what is on screen: tickers and themes by frequency, holdings first; sources from the Runtime. */
export function useFilterOptions(items: NewsItem[], sources: NewsSource[] | null) {
  return useMemo(() => {
    const tick = new Map<string, { n: number; held: boolean }>();
    const theme = new Map<string, number>();
    for (const it of items) {
      for (const t of it.tickers) {
        const cur = tick.get(t) ?? { n: 0, held: false };
        tick.set(t, { n: cur.n + 1, held: cur.held || it.in_portfolio || it.in_watchlist });
      }
      for (const t of it.themes) theme.set(t, (theme.get(t) ?? 0) + 1);
    }
    const tickers: Option[] = [...tick.entries()]
      .sort((a, b) => Number(b[1].held) - Number(a[1].held) || b[1].n - a[1].n || a[0].localeCompare(b[0]))
      .slice(0, 24)
      .map(([t, v]) => ({ value: t, label: t, hint: String(v.n) }));
    const themes: Option[] = [...theme.entries()].sort((a, b) => b[1] - a[1]).slice(0, 20).map(([t, n]) => ({ value: t, label: t, hint: String(n) }));
    const srcs: Option[] = (sources ?? []).map((s) => ({ value: String(s.id), label: s.name, hint: providerLabel(s.provider) }));
    const providers: Option[] = Object.entries(PROVIDER_LABEL).map(([v, l]) => ({ value: v, label: l }));
    return { tickers, themes, sources: srcs, providers };
  }, [items, sources]);
}

/** Search as you type, written to the URL after a short pause. */
function useDebounced(value: string, onCommit: (v: string) => void, ms = 300) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  useEffect(() => {
    if (draft === value) return;
    const t = setTimeout(() => onCommit(draft.trim()), ms);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);
  return [draft, setDraft] as const;
}

export function SearchField({ value, onChange, className }: { value: string; onChange: (v: string) => void; className?: string }) {
  const [draft, setDraft] = useDebounced(value, onChange);
  return (
    <label className={cn("flex h-7 items-center gap-1.5 rounded-control border border-line-strong bg-[oklch(0.205_0.008_260)] px-2 transition-colors focus-within:border-accent-c/70", className)}>
      <Search className="size-3.5 shrink-0 text-fg-subtle" aria-hidden />
      <input
        type="search"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onChange(draft.trim());
          if (e.key === "Escape") {
            setDraft("");
            onChange("");
          }
        }}
        placeholder="Cerca nei titoli e nei sommari"
        aria-label="Cerca nelle notizie"
        className="min-w-0 flex-1 bg-transparent text-xs text-fg outline-none placeholder:text-fg-subtle [&::-webkit-search-cancel-button]:hidden"
      />
      {draft && (
        <button type="button" aria-label="Svuota la ricerca" onClick={() => (setDraft(""), onChange(""))} className="grid size-4 place-items-center rounded-tag text-fg-subtle hover:text-fg">
          <X className="size-3" />
        </button>
      )}
    </label>
  );
}

function ScopeControl({ value, onChange, full }: { value: NewsScope; onChange: (v: NewsScope) => void; full?: boolean }) {
  return (
    <div role="radiogroup" aria-label="Ambito" className={cn("seg", full && "flex w-full")}>
      {(Object.keys(SCOPE_LABEL) as NewsScope[]).map((s) => (
        <button key={s} type="button" role="radio" aria-checked={value === s} onClick={() => onChange(s)} className={cn("seg-item", full && "flex-1 justify-center")}>
          {SCOPE_LABEL[s]}
        </button>
      ))}
    </div>
  );
}

function FilterMenu({ label, value, display, options, onChange, custom }: { label: string; value: string; display?: string; options: Option[]; onChange: (v: string) => void; custom?: boolean }) {
  const [typed, setTyped] = useState("");
  const set = value !== "";
  return (
    <span className="inline-flex items-center">
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "inline-flex h-7 shrink-0 items-center gap-1 rounded-control px-2 text-xs font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/60",
          set ? "bg-selected text-fg shadow-[inset_0_0_0_1px_oklch(0.7_0.15_251/0.35)]" : "text-fg-muted hover:bg-hover hover:text-fg",
        )}
      >
        {label}
        {set && <span className="max-w-28 truncate text-fg">: {display ?? value}</span>}
        <ChevronDown className="size-3 text-fg-subtle" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-[min(420px,70vh)] w-60 overflow-y-auto">
        {custom && (
          <>
            <form
              className="p-1"
              onSubmit={(e) => {
                e.preventDefault();
                if (typed.trim()) onChange(typed.trim().toUpperCase());
                setTyped("");
              }}
            >
              <input
                value={typed}
                onChange={(e) => setTyped(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.stopPropagation()}
                placeholder="Simbolo, poi Invio"
                aria-label="Simbolo del ticker"
                className="num h-7 w-full rounded-item border border-line-strong bg-[oklch(0.205_0.008_260)] px-2 text-xs text-fg outline-none placeholder:text-fg-subtle focus:border-accent-c/70"
              />
            </form>
            <DropdownMenuSeparator />
          </>
        )}
        {set && (
          <>
            <DropdownMenuItem onSelect={() => onChange("")} className="text-xs text-fg-muted">
              <X className="size-3.5" /> Togli il filtro
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        )}
        {options.length === 0 ? (
          <DropdownMenuLabel className="text-2xs font-normal text-fg-subtle">Nessuna voce nelle notizie caricate</DropdownMenuLabel>
        ) : (
          options.map((o) => (
            <DropdownMenuItem key={o.value} onSelect={() => onChange(o.value)} className="gap-2 text-xs">
              <Check className={cn("size-3.5", o.value === value ? "opacity-100" : "opacity-0")} />
              <span className="min-w-0 flex-1 truncate">{o.label}</span>
              {o.hint && <span className="num shrink-0 text-2xs text-fg-subtle">{o.hint}</span>}
            </DropdownMenuItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
    {set && (
      <button type="button" onClick={() => onChange("")} aria-label={`Togli il filtro ${label}`} title={`Togli il filtro ${label}`} className="-ml-1 grid size-7 place-items-center rounded-item text-fg-subtle outline-none transition-colors hover:bg-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-ring/60">
        <X className="size-3" />
      </button>
    )}
    </span>
  );
}

type Opts = ReturnType<typeof useFilterOptions>;

const sourceName = (opts: Opts, id: string) => opts.sources.find((s) => s.value === id)?.label ?? `fonte ${id}`;

export function DesktopFilters({ ctl, opts, end }: { ctl: Ctl; opts: Opts; end?: ReactNode }) {
  const { filters: f, setFilter } = ctl;
  return (
    <div data-part="filters" className="flex shrink-0 flex-wrap items-center gap-1.5 px-2.5 pb-2">
      <ScopeControl value={f.scope} onChange={(v) => setFilter("scope", v)} />
      <span aria-hidden className="mx-0.5 h-4 w-px bg-line" />
      <FilterMenu label="Ticker" value={f.ticker} options={opts.tickers} onChange={(v) => setFilter("ticker", v)} custom />
      <FilterMenu label="Tema" value={f.theme} options={opts.themes} onChange={(v) => setFilter("theme", v)} />
      <FilterMenu label="Fonte" value={f.source_id} display={f.source_id ? sourceName(opts, f.source_id) : undefined} options={opts.sources} onChange={(v) => setFilter("source_id", v)} />
      <FilterMenu label="Provider" value={f.provider} display={f.provider ? providerLabel(f.provider) : undefined} options={opts.providers} onChange={(v) => setFilter("provider", v)} />
      {ctl.active > 0 && (
        <Button variant="ghost" size="xs" onClick={ctl.clearFilters} className="text-fg-subtle">
          Azzera
        </Button>
      )}
      {end && <div className="ml-auto flex items-center gap-1.5">{end}</div>}
    </div>
  );
}

function ChipGroup({ label, value, options, onChange }: { label: string; value: string; options: Option[]; onChange: (v: string) => void }) {
  if (!options.length) return null;
  return (
    <fieldset className="min-w-0">
      <legend className="mb-1.5 text-2xs font-medium text-fg-subtle">{label}</legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const on = o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(on ? "" : o.value)}
              className={cn("inline-flex h-8 items-center gap-1.5 rounded-item px-2.5 text-xs font-medium transition-colors", on ? "bg-selected text-fg shadow-[inset_0_0_0_1px_oklch(0.7_0.15_251/0.4)]" : "bg-hover text-fg-muted")}
            >
              {o.label}
              {o.hint && <span className="num text-2xs text-fg-subtle">{o.hint}</span>}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

/** Phone: one Filtri button with the active count; everything else in a bottom sheet. */
export function MobileFilters({ ctl, opts }: { ctl: Ctl; opts: Opts }) {
  const { filters: f, setFilter } = ctl;
  return (
    <Sheet>
      <SheetTrigger asChild>
        <button type="button" aria-label={`Filtri${ctl.active ? `, ${ctl.active} attivi` : ""}`} className="relative inline-flex h-9 shrink-0 items-center gap-1.5 rounded-control bg-ground px-3 text-xs font-medium text-fg">
          <SlidersHorizontal className="size-4 text-fg-subtle" /> Filtri
          {ctl.active > 0 && <span className="num rounded-tag bg-selected px-1 text-[10px] leading-4 text-fg">{ctl.active}</span>}
        </button>
      </SheetTrigger>
      <SheetContent side="bottom" className="max-h-[85vh] gap-0 overflow-y-auto rounded-t-tile border-0 bg-ground p-0 [&>button]:hidden">
        <div className="sticky top-0 flex items-center gap-2 bg-ground px-4 pb-2 pt-4">
          <SheetTitle className="text-[15px] font-semibold text-fg">Filtri</SheetTitle>
          <SheetDescription className="sr-only">Filtra il flusso delle notizie</SheetDescription>
          {ctl.active > 0 && (
            <Button variant="ghost" size="sm" onClick={ctl.clearFilters} className="ml-auto">
              Azzera
            </Button>
          )}
        </div>
        <div className="space-y-4 px-4 pb-6 pt-1">
          <ScopeControl value={f.scope} onChange={(v) => setFilter("scope", v)} full />
          <ChipGroup label="Ticker" value={f.ticker} options={f.ticker && !opts.tickers.some((o) => o.value === f.ticker) ? [{ value: f.ticker, label: f.ticker }, ...opts.tickers] : opts.tickers} onChange={(v) => setFilter("ticker", v)} />
          <ChipGroup label="Tema" value={f.theme} options={opts.themes} onChange={(v) => setFilter("theme", v)} />
          <ChipGroup label="Fonte" value={f.source_id} options={opts.sources} onChange={(v) => setFilter("source_id", v)} />
          <ChipGroup label="Provider" value={f.provider} options={opts.providers} onChange={(v) => setFilter("provider", v)} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
