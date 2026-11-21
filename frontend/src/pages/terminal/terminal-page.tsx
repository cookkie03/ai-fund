import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import type { ChartDrawing } from "@/features/chart/chart-state";
import { orderBucket } from "@/lib/orders";
import { useOrders, useWatchlist } from "@/lib/runtime/hooks";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { ActivityPanel } from "./activity-panel";
import { ChartPanel } from "./chart-panel";
import { OrdersDock } from "./orders-dock";
import { Watchlist } from "./watchlist";

const ACTIVITY_KEY = "cockpit.terminal.activity";

function readActivityOpen() {
  try {
    return localStorage.getItem(ACTIVITY_KEY) !== "closed";
  } catch {
    return true;
  }
}

type MobileTab = "watchlist" | "activity" | "orders";
const MOBILE_TABS: { id: MobileTab; label: string }[] = [
  { id: "watchlist", label: "Watchlist" },
  { id: "activity", label: "Attività" },
  { id: "orders", label: "Ordini" },
];

export function TerminalPage() {
  const [params, setParams] = useSearchParams();
  const watchlist = useWatchlist();
  const orders = useOrders();
  const pendingCount = (orders.data ?? []).filter((o) => orderBucket(o) === "pending").length;
  const wide = useMediaQuery("(min-width: 1280px)");
  const tablet = useMediaQuery("(min-width: 768px)");

  const requested = params.get("t")?.toUpperCase() ?? null;
  const first = watchlist.data?.[0]?.ticker ?? null;
  const selected = requested ?? first;

  const select = useCallback(
    (t: string) => {
      setParams(
        (p) => {
          const next = new URLSearchParams(p);
          next.set("t", t);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const [activityOpen, setActivityOpen] = useState(readActivityOpen);
  useEffect(() => {
    try {
      localStorage.setItem(ACTIVITY_KEY, activityOpen ? "open" : "closed");
    } catch {
      /* storage unavailable: the choice lasts for this visit */
    }
  }, [activityOpen]);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [mobileTab, setMobileTab] = useState<MobileTab>("watchlist");

  const [drawings, setDrawings] = useState<ChartDrawing[]>([]);
  const strikeRef = useRef<(id: string) => void>(() => {});
  const onDrawings = useCallback((d: ChartDrawing[], strike: (id: string) => void) => {
    setDrawings(d);
    strikeRef.current = strike;
  }, []);
  const [focus, setFocus] = useState<{ id: string; nonce: number } | null>(null);
  const focusDrawing = useCallback((id: string) => {
    setFocus({ id, nonce: Date.now() });
    setSheetOpen(false);
  }, []);

  useEffect(() => {
    document.title = selected ? `${selected} · Terminale` : "Terminale";
  }, [selected]);

  const activity = (opts: { onCollapse?: () => void; className?: string }) => (
    <ActivityPanel
      ticker={selected}
      drawings={drawings.filter((d) => d.ticker === selected)}
      onFocusDrawing={focusDrawing}
     
      onStrike={(id) => strikeRef.current(id)}
      {...opts}
    />
  );

  if (!tablet) {
    return (
      <div className="flex min-h-full min-w-0 flex-1 flex-col overflow-y-auto">
        <div className="flex h-[56vh] min-h-[320px] shrink-0 border-b border-line">
          <ChartPanel symbol={selected} focusDrawing={focus} onDrawings={onDrawings} compact />
        </div>
        {pendingCount > 0 && mobileTab !== "orders" && (
          <button
            type="button"
            data-action="approve"
            onClick={() => setMobileTab("orders")}
            className="flex h-10 shrink-0 items-center gap-2 border-b border-line bg-warn-soft px-4 text-left text-xs"
          >
            <span className="size-1.5 rounded-full bg-warn" aria-hidden />
            <span className="font-medium text-fg">
              {pendingCount === 1 ? "1 ordine da approvare" : `${pendingCount} ordini da approvare`}
            </span>
            <span className="ml-auto font-medium text-accent-c">Rivedi</span>
          </button>
        )}
        <div role="tablist" aria-label="Sezioni del Terminale" className="sticky top-0 z-10 flex h-10 shrink-0 border-b border-line bg-panel">
          {MOBILE_TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={mobileTab === t.id}
              onClick={() => setMobileTab(t.id)}
              className={cn(
                "relative flex-1 text-xs font-medium transition-colors",
                mobileTab === t.id ? "text-fg after:absolute after:inset-x-4 after:bottom-0 after:h-0.5 after:rounded-full after:bg-accent-c" : "text-fg-subtle",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex min-h-[50vh] flex-1 flex-col">
          {mobileTab === "watchlist" && <Watchlist selected={selected} onSelect={select} className="flex-1" />}
          {mobileTab === "activity" && activity({ className: "flex-1" })}
          {mobileTab === "orders" && <OrdersDock selected={selected} onSelect={select} className="flex-1" />}
        </div>
      </div>
    );
  }

  return (
    <div data-region="workspace" className="flex h-full min-h-0 min-w-0 flex-1">
      <Watchlist selected={selected} onSelect={select} className="w-[272px] shrink-0 border-r border-line" />
      <div data-region="stage" className="flex min-w-0 flex-1 flex-col">
        <div data-region="upper" className="flex min-h-0 flex-1">
          <ChartPanel
            symbol={selected}
            focusDrawing={focus}
           
            onDrawings={onDrawings}
            activityCollapsed={wide ? !activityOpen : true}
            onExpandActivity={() => (wide ? setActivityOpen(true) : setSheetOpen(true))}
          />
          {wide && activityOpen && activity({ onCollapse: () => setActivityOpen(false), className: "w-[304px] shrink-0 border-l border-line" })}
        </div>
        <OrdersDock selected={selected} onSelect={select} className="h-[232px] shrink-0 border-t border-line" />
      </div>
      {!wide && (
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetContent side="right" className="w-[340px] gap-0 border-line-strong bg-panel p-0 sm:max-w-[340px]">
            <SheetTitle className="sr-only">Attività sullo strumento</SheetTitle>
            {activity({ onCollapse: () => setSheetOpen(false), className: "h-full" })}
          </SheetContent>
        </Sheet>
      )}
    </div>
  );
}
