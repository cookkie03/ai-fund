import type { DrawingKind } from "lightweight-charts-drawing";
import { ChartNoAxesCombined, Eye, FileText, EyeOff, Minus, MousePointer2, MoveUpRight, RectangleHorizontal, RotateCw, Rows3, Slash } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AuthorChip } from "@/components/author-chip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ChartView, type PriceMark } from "@/features/chart/chart-view";
import {
  INDICATORS,
  KIND_LABEL,
  TIMEFRAMES,
  TOOLBAR_KINDS,
  fromAnnotation,
  loadPrefs,
  savePrefs,
  toRuntimeDrawing,
  type ChartDrawing,
  type IndicatorId,
} from "@/features/chart/chart-state";
import { author, type Author } from "@/lib/authors";
import { fmtAge, fmtDateTime, fmtPct, fmtPrice } from "@/lib/format";
import { orderBucket, orderFigures } from "@/lib/orders";
import { useAnnotations, useBars, useCommand, useIndicators, useOrders, useTrades } from "@/lib/runtime/hooks";
import { useNow } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { useFreshness } from "@/shell/status";

const TOOL_ICON: Partial<Record<DrawingKind, typeof Slash>> = {
  "trend-line": Slash,
  "horizontal-line": Minus,
  ray: MoveUpRight,
  rectangle: RectangleHorizontal,
  "fib-retracement": Rows3,
  "parallel-channel": ChartNoAxesCombined,
};

function ToolButton({ label, active, onClick, children, disabled, shortcut }: { label: string; active?: boolean; onClick: () => void; children: ReactNode; disabled?: boolean; shortcut?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            aria-label={label}
            aria-pressed={active}
            onClick={onClick}
            disabled={disabled}
            className={cn(
              "grid size-6 place-items-center rounded-item transition-[background-color,color,transform] duration-150 active:scale-[0.92] disabled:opacity-35",
              active ? "bg-raised text-fg shadow-[0_1px_2px_oklch(0_0_0/0.45),inset_0_0.5px_0_oklch(1_0_0/0.08)]" : "text-fg-subtle hover:text-fg",
            )}
          >
            {children}
          </button>
        }
      />
      <TooltipContent>
        {label}
        {shortcut && <kbd className="ml-2 rounded-tag bg-hover px-1 py-px font-sans text-2xs text-fg-subtle">{shortcut}</kbd>}
      </TooltipContent>
    </Tooltip>
  );
}

function AuthorLayers({
  authors,
  hidden,
  onToggle,
  onHover,
}: {
  authors: { author: Author; count: number }[];
  hidden: string[];
  onToggle: (id: string) => void;
  onHover: (id: string | null) => void;
}) {
  if (!authors.length) return null;
  return (
    <div data-part="layers" className="flex flex-wrap items-center gap-1" role="group" aria-label="Livelli per autore">
      {authors.map(({ author: a, count }) => {
        const off = hidden.includes(a.id);
        return (
          <button
            key={a.id}
            type="button"
            aria-pressed={!off}
            onClick={() => onToggle(a.id)}
            onMouseEnter={() => !off && onHover(a.id)}
            onMouseLeave={() => onHover(null)}
            onFocus={() => !off && onHover(a.id)}
            onBlur={() => onHover(null)}
            title={`${off ? "Mostra" : "Nascondi"} i disegni di ${a.name}`}
            className={cn(
              "inline-flex h-6 items-center gap-1.5 rounded-item border bg-ground/85 pl-1 pr-1.5 text-2xs backdrop-blur-[2px] transition-colors",
              off ? "border-line text-fg-subtle" : "border-line-strong text-fg-muted hover:border-fg-faint hover:text-fg",
            )}
          >
            <span className={cn(off && "opacity-40 grayscale")}>
              <AuthorChip author={a} size="xs" label={false} tooltip={a.name} />
            </span>
            <span className={cn(off && "line-through")}>{a.short}</span>
            <span className="num text-fg-subtle">{count}</span>
            {off ? <EyeOff className="size-3" /> : <Eye className="size-3 opacity-0 group-hover:opacity-100" />}
          </button>
        );
      })}
    </div>
  );
}

function Overlay({ children }: { children: ReactNode }) {
  return <div className="absolute inset-0 z-20 grid place-items-center bg-ground/70 p-6 text-center">{children}</div>;
}

export function ChartPanel({
  symbol,
  focusDrawing,
  onDrawings,
  compact = false,
  className,
}: {
  symbol: string | null;
  focusDrawing: { id: string; nonce: number } | null;
  onDrawings: (d: ChartDrawing[], strike: (id: string) => void) => void;
  compact?: boolean;
  className?: string;
}) {
  const { writable } = useShell();
  const freshness = useFreshness();
  const now = useNow(30_000);
  const [prefs, setPrefs] = useState(loadPrefs);
  const [tool, setTool] = useState<DrawingKind | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [drawingsVisible, setDrawingsVisible] = useState(true);
  const [optimistic, setOptimistic] = useState<Record<string, ChartDrawing | null>>({});

  useEffect(() => savePrefs(prefs), [prefs]);
  useEffect(() => setTool(null), [symbol]);

  const indicatorNames = useMemo(() => INDICATORS.filter((s) => prefs.indicators.includes(s.id)).map((s) => s.request), [prefs.indicators]);
  const indicatorsQ = useIndicators(symbol, indicatorNames.length ? indicatorNames : ["ema20"], prefs.timeframe, 600);
  const barsQ = useBars(symbol, prefs.timeframe, 600);
  const annotationsQ = useAnnotations(symbol);
  const orders = useOrders();
  const trades = useTrades();
  const timeframe = prefs.timeframe ?? indicatorsQ.data?.timeframe ?? "1h";

  // Server truth, with this session's not-yet-confirmed edits laid over it.
  const serverDrawings = useMemo(() => (annotationsQ.data ?? []).map(fromAnnotation).filter((d): d is ChartDrawing => d !== null), [annotationsQ.data]);
  useEffect(() => setOptimistic({}), [annotationsQ.dataUpdatedAt]);
  const drawings = useMemo(() => {
    const map = new Map(serverDrawings.map((d) => [d.id, d]));
    for (const [id, d] of Object.entries(optimistic)) {
      if (d === null) {
        const cur = map.get(id);
        if (cur) map.set(id, { ...cur, status: "struck", struckBy: "cockpit" });
      } else map.set(id, d);
    }
    return [...map.values()];
  }, [serverDrawings, optimistic]);
  const activeDrawings = useMemo(() => drawings.filter((d) => d.status === "active"), [drawings]);

  const upsert = useCommand("upsert_annotation", { invalidate: [["annotations"]] });
  const strike = useCommand("strike_annotation", { invalidate: [["annotations"]] });
  const strikeId = (id: string) => {
    setOptimistic((o) => ({ ...o, [id]: null }));
    strike.mutate({ id });
  };

  useEffect(() => {
    onDrawings(drawings, strikeId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawings]);

  const authors = useMemo(() => {
    const m = new Map<string, { author: Author; count: number }>();
    for (const d of activeDrawings) {
      const a = author(d.author);
      const e = m.get(a.id) ?? { author: a, count: 0 };
      e.count++;
      m.set(a.id, e);
    }
    return [...m.values()].sort((x, y) => (x.author.kind === "human" ? -1 : y.author.kind === "human" ? 1 : y.count - x.count));
  }, [activeDrawings]);

  const marks = useMemo<PriceMark[]>(() => {
    if (!symbol) return [];
    const out: PriceMark[] = [];
    const all = orders.data ?? [];
    for (const t of trades.data ?? []) {
      if (t.ticker !== symbol || t.closed_ts) continue;
      const entryOrder = all.find((o) => o.id === t.entry_order_id);
      out.push({ id: `t${t.id}-e`, price: t.entry_price, title: `Entry ×${t.qty}`, tone: "entry" });
      if (entryOrder) {
        const f = orderFigures(entryOrder);
        if (f.tp) out.push({ id: `t${t.id}-tp`, price: f.tp, title: "TP", tone: "tp" });
        if (f.stop) out.push({ id: `t${t.id}-sl`, price: f.stop, title: "SL", tone: "sl" });
      }
    }
    for (const o of all) {
      if (o.ticker !== symbol) continue;
      const b = orderBucket(o);
      if (b === "done") continue;
      const f = orderFigures(o);
      const tag = b === "pending" ? `In attesa #${o.id}` : `Limite #${o.id}`;
      if (f.entry) out.push({ id: `o${o.id}-e`, price: f.entry, title: tag, tone: "pending" });
      if (f.tp) out.push({ id: `o${o.id}-tp`, price: f.tp, title: `TP #${o.id}`, tone: "pending" });
      if (f.stop) out.push({ id: `o${o.id}-sl`, price: f.stop, title: `SL #${o.id}`, tone: "pending" });
    }
    return out;
  }, [symbol, orders.data, trades.data]);

  const bars = barsQ.data ?? [];
  const last = bars.at(-1);
  const first = bars.length > 1 ? bars.findLast((b) => new Date(b.time * 1000).toDateString() !== new Date(last!.time * 1000).toDateString()) : undefined;
  const dayChange = last && first ? ((last.close - first.close) / first.close) * 100 : null;
  const hiddenAll = prefs.hiddenAuthors;

  const toggleIndicator = (id: IndicatorId) =>
    setPrefs((p) => ({ ...p, indicators: p.indicators.includes(id) ? p.indicators.filter((x) => x !== id) : [...p.indicators, id] }));

  const toggleAuthor = (id: string) =>
    setPrefs((p) => ({ ...p, hiddenAuthors: p.hiddenAuthors.includes(id) ? p.hiddenAuthors.filter((x) => x !== id) : [...p.hiddenAuthors, id] }));

  const effectiveHidden = drawingsVisible ? hiddenAll : authors.map((a) => a.author.id);

  return (
    <section id="chart" data-region="chart" aria-label="Grafico" className={cn("@container flex min-h-0 min-w-0 flex-1 flex-col bg-ground", className)}>
      {/* header: the instrument and its price lead, controls sit to the right */}
      <div data-region="chart-toolbar" className={cn("flex shrink-0 items-center gap-2 overflow-x-auto px-4", compact ? "h-14" : "h-[68px]")}>
        <div className="mr-3 flex min-w-0 shrink-0 flex-col justify-center">
          {symbol ? (
            <Link
              to={`/ticker/${symbol}`}
              data-role="symbol"
              title={`Apri la scheda di ${symbol}`}
              className="group/sym inline-flex items-center gap-1 self-start rounded-item text-[13px] font-semibold leading-4 tracking-[-0.005em] text-fg-muted outline-none hover:text-fg focus-visible:ring-2 focus-visible:ring-ring/60"
            >
              {symbol}
              <FileText className="size-3 opacity-60 group-hover/sym:opacity-100" strokeWidth={1.75} aria-hidden />
              <span className="sr-only">: apri la scheda</span>
            </Link>
          ) : (
            <span data-role="symbol" className="text-[13px] font-semibold leading-4 tracking-[-0.005em] text-fg-muted">—</span>
          )}
          <span className="flex items-baseline gap-2.5">
            {last ? (
              <span data-role="price" className={cn("num font-semibold leading-tight tracking-[-0.025em] text-fg", compact ? "text-[22px]" : "text-[30px]")}>{fmtPrice(last.close)}</span>
            ) : (
              <span className={cn("leading-tight text-fg-faint", compact ? "text-[22px]" : "text-[30px]")}>—</span>
            )}
            {dayChange !== null && (
              <Badge
                variant="outline"
                data-role="change"
                data-dir={dayChange >= 0 ? "up" : "down"}
                className={cn("num -translate-y-1 rounded-tag px-1.5 py-0.5 text-xs font-semibold border-transparent", dayChange >= 0 ? "bg-up-soft text-up" : "bg-down-soft text-down")}
              >
                {fmtPct(dayChange)}
              </Badge>
            )}
          </span>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <div role="radiogroup" aria-label="Timeframe" className="seg">
            {TIMEFRAMES.map((tf) => (
              <button key={tf.id} role="radio" aria-checked={timeframe === tf.id} onClick={() => setPrefs((p) => ({ ...p, timeframe: tf.id }))} className="seg-item num px-2.5">
                {tf.label}
              </button>
            ))}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-control px-2.5 text-xs font-medium text-fg-muted transition-colors hover:bg-hover hover:text-fg data-[state=open]:bg-hover data-[state=open]:text-fg">
              <ChartNoAxesCombined className="size-3.5" strokeWidth={1.75} /> <span className="sr-only @[52rem]:not-sr-only">Indicatori</span>
              <span className="num rounded-tag bg-hover px-1 text-[10px] leading-4 text-fg-subtle">{prefs.indicators.length}</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuLabel className="text-2xs font-normal text-fg-subtle">Calcolati dal Runtime, gli stessi valori che leggono gli agenti</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {INDICATORS.map((s) => (
                <DropdownMenuCheckboxItem key={s.id} checked={prefs.indicators.includes(s.id)} onCheckedChange={() => toggleIndicator(s.id)} onSelect={(e) => e.preventDefault()} className="text-xs">
                  <span className="flex flex-col">
                    <span className="text-fg">{s.label}</span>
                    <span className="text-2xs text-fg-subtle">{s.description}</span>
                  </span>
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <div className={cn("seg", compact && "hidden")} role="toolbar" aria-label="Strumenti di disegno">
            <ToolButton label="Cursore" active={tool === null} onClick={() => setTool(null)} shortcut="Esc">
              <MousePointer2 className="size-3.5" strokeWidth={1.75} />
            </ToolButton>
            {TOOLBAR_KINDS.map((k) => {
              const Icon = TOOL_ICON[k] ?? Slash;
              return (
                <ToolButton key={k} label={KIND_LABEL[k] ?? k} active={tool === k} onClick={() => setTool(tool === k ? null : k)} disabled={!writable || !symbol || !bars.length}>
                  <Icon className="size-3.5" strokeWidth={1.75} />
                </ToolButton>
              );
            })}
            <span className="mx-0.5 h-3.5 w-px bg-line-strong" aria-hidden />
            <ToolButton label={drawingsVisible ? "Nascondi tutti i disegni" : "Mostra i disegni"} active={!drawingsVisible} onClick={() => setDrawingsVisible((v) => !v)}>
              {drawingsVisible ? <Eye className="size-3.5" strokeWidth={1.75} /> : <EyeOff className="size-3.5" strokeWidth={1.75} />}
            </ToolButton>
          </div>
          {last && !compact && (
            <span className="hidden text-2xs text-fg-subtle 2xl:inline">
              Ultima barra <span className="num text-fg-muted">{fmtDateTime(last.time)}</span>
            </span>
          )}
          {symbol && bars.length > 0 && (freshness.state === "stale" || freshness.state === "down") && (
            <Badge variant="outline" role="status" className="h-6 gap-1.5 rounded-item bg-warn-soft px-2 text-2xs text-warn border-transparent">
              <span className="size-1.5 rounded-full bg-warn" style={{ animation: "status-pulse 1.6s ease-in-out infinite" }} aria-hidden />
              {freshness.age !== null && freshness.age >= 60_000 ? `Non in tempo reale · ${fmtAge(now - freshness.age, now)} fa` : "Non in tempo reale"}
            </Badge>
          )}
        </div>
      </div>

      {/* chart */}
      <div data-region="chart-body" className="relative min-h-0 flex-1">
        {symbol && (
          <ChartView
            key={symbol}
            className="absolute inset-0"
            symbol={symbol}
            timeframe={timeframe}
            bars={bars}
            indicators={indicatorsQ.data && indicatorsQ.data.ticker === symbol ? indicatorsQ.data : undefined}
            enabled={prefs.indicators}
            drawings={activeDrawings}
            hiddenAuthors={effectiveHidden}
            highlightAuthor={highlight}
            focusDrawing={focusDrawing}
            marks={marks}
            tool={tool}
            interactive={writable}
            onToolChange={setTool}
            onCreate={(d) => {
              const draft: ChartDrawing = {
                ...d,
                ticker: symbol,
                timeframe,
                author: "cockpit",
                status: "active",
                struckBy: null,
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
              };
              setOptimistic((o) => ({ ...o, [d.id]: draft }));
              upsert.mutate({ id: d.id, ticker: symbol, timeframe, drawing: toRuntimeDrawing(d) });
            }}
            onUpdate={(d) => {
              const cur = drawings.find((x) => x.id === d.id);
              if (!cur || author(cur.author).kind !== "human") return;
              setOptimistic((o) => ({ ...o, [d.id]: { ...cur, points: d.points, updatedAt: new Date().toISOString() } }));
              upsert.mutate({ id: d.id, ticker: symbol, timeframe: cur.timeframe ?? timeframe, drawing: toRuntimeDrawing({ ...cur, points: d.points }) });
            }}
            onRemove={(id) => {
              const cur = drawings.find((x) => x.id === id);
              if (cur && author(cur.author).kind === "human") strikeId(id);
            }}
          >
            <AuthorLayers authors={authors} hidden={effectiveHidden} onToggle={toggleAuthor} onHover={setHighlight} />
          </ChartView>
        )}

        {!symbol && freshness.state === "down" ? (
          <Overlay>
            <div className="max-w-sm">
              <p className="text-sm text-fg">Grafico non disponibile</p>
              <p className="mt-1 text-xs leading-relaxed text-fg-muted">Le barre arrivano dal Runtime: il grafico si carica appena torna raggiungibile.</p>
            </div>
          </Overlay>
        ) : !symbol ? (
          <Overlay>
            <div className="max-w-sm">
              <p className="text-sm text-fg">Nessun ticker selezionato</p>
              <p className="mt-1 text-xs leading-relaxed text-fg-muted">Aggiungi un ticker alla watchlist per vedere il grafico che usa il Technical Analyst.</p>
            </div>
          </Overlay>
        ) : barsQ.isPending ? (
          <div className="absolute inset-0 z-20 flex flex-col gap-3 bg-ground p-4" aria-busy aria-label="Caricamento del grafico">
            <div className="h-3 w-72 animate-pulse rounded-item bg-hover" />
            <div className="flex flex-1 items-end gap-[3px] opacity-60">
              {Array.from({ length: 64 }).map((_, i) => (
                <div key={i} className="flex-1 animate-pulse rounded-[1px] bg-hover" style={{ height: `${30 + 40 * Math.abs(Math.sin(i * 0.37)) + 15 * Math.sin(i * 1.7)}%` }} />
              ))}
            </div>
          </div>
        ) : barsQ.isError && !bars.length ? (
          <Overlay>
            <div className="max-w-sm">
              <p className="text-sm text-down">Barre non disponibili per {symbol}</p>
              <p className="mt-1 text-xs text-fg-muted">{barsQ.error.message}</p>
              <Button variant="outline" size="sm" className="mt-3" onClick={() => barsQ.refetch()}>
                <RotateCw className="size-3.5" /> Riprova
              </Button>
            </div>
          </Overlay>
        ) : !bars.length ? (
          <Overlay>
            <div className="max-w-sm">
              <p className="text-sm text-fg">Nessuna barra per {symbol}</p>
              <p className="mt-1 text-xs leading-relaxed text-fg-muted">
                Il provider dati non ha restituito barre {timeframe === "1d" ? "giornaliere" : timeframe} per questo ticker. Prova un altro timeframe o verifica il simbolo.
              </p>
            </div>
          </Overlay>
        ) : null}


      </div>
      {upsert.isError && <span className="sr-only">Il disegno non è stato salvato</span>}
    </section>
  );
}
