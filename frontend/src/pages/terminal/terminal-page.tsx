import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { useSearchParams } from "react-router-dom";
import { Gutter } from "@/components/gutter";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ChartDrawing } from "@/features/chart/chart-state";
import { orderBucket } from "@/lib/orders";
import { useOrders, useWatchlist } from "@/lib/runtime/hooks";
import { useMediaQuery } from "@/lib/use-media-query";
import { PANEL_LIMITS, useShell } from "@/shell/shell-state";
import { ActivityPanel } from "./activity-panel";
import { ChartPanel } from "./chart-panel";
import { OrdersDock } from "./orders-dock";
import { Watchlist } from "./watchlist";

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
  const { layout, setPanelOpen, setPanelSize } = useShell();
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
  }, []);

  useEffect(() => {
    document.title = selected ? `${selected} · Terminale` : "Terminale";
  }, [selected]);

  const activity = (opts: { onCollapse?: () => void; className?: string; style?: CSSProperties }) => (
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
        <div className="flex h-[56vh] min-h-[320px] shrink-0">
          <ChartPanel symbol={selected} focusDrawing={focus} onDrawings={onDrawings} compact />
        </div>
        {pendingCount > 0 && mobileTab !== "orders" && (
          <button
            type="button"
            data-action="approve"
            onClick={() => setMobileTab("orders")}
            className="mx-2 mt-2 flex h-10 shrink-0 items-center gap-2 rounded-control bg-warn-soft px-3 text-left text-xs transition-colors hover:bg-warn-soft/80"
          >
            <Badge variant="outline" className="border-warn/40 text-warn bg-transparent gap-1.5 font-normal">
              <span className="size-1.5 rounded-full bg-warn" aria-hidden />
              {pendingCount === 1 ? "1 ordine da approvare" : `${pendingCount} ordini da approvare`}
            </Badge>
            <span className="ml-auto font-medium text-accent-c">Rivedi</span>
          </button>
        )}
        <Tabs value={mobileTab} onValueChange={(v) => setMobileTab(v as MobileTab)} className="sticky top-0 z-10 mx-2 mt-2">
          <TabsList className="w-full h-9 bg-ground">
            {MOBILE_TABS.map((t) => (
              <TabsTrigger key={t.id} value={t.id} className="flex-1 text-xs">
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="m-2 flex min-h-[50vh] flex-1 flex-col overflow-hidden rounded-tile bg-ground">
          {mobileTab === "watchlist" && <Watchlist selected={selected} onSelect={select} className="flex-1" />}
          {mobileTab === "activity" && activity({ className: "flex-1" })}
          {mobileTab === "orders" && <OrdersDock selected={selected} onSelect={select} className="flex-1" />}
        </div>
      </div>
    );
  }

  const { open, size } = layout;
  const resetTo = (id: "left" | "right" | "bottom") => () => setPanelSize(id, PANEL_LIMITS[id].initial);

  return (
    <div data-region="workspace" className="flex h-full min-h-0 min-w-0 flex-1 pb-2.5 pr-2.5">
      {open.left && (
        <>
          <Watchlist
            selected={selected}
            onSelect={select}
            onHide={() => setPanelOpen("left", false)}
            className="tile-enter-left shrink-0 overflow-hidden rounded-tile"
            style={{ width: size.left }}
          />
          <Gutter
            orientation="vertical"
            label="Larghezza della watchlist"
            value={size.left}
            min={PANEL_LIMITS.left.min}
            max={PANEL_LIMITS.left.max}
            direction={1}
            onResize={(px) => setPanelSize("left", px)}
            onReset={resetTo("left")}
          />
        </>
      )}
      <div data-region="stage" className="flex min-w-0 flex-1 flex-col">
        <div data-region="upper" className="flex min-h-0 flex-1">
          <ChartPanel symbol={selected} focusDrawing={focus} onDrawings={onDrawings} className="overflow-hidden rounded-tile" />
          {open.right && (
            <>
              <Gutter
                orientation="vertical"
                label="Larghezza del pannello attività"
                value={size.right}
                min={PANEL_LIMITS.right.min}
                max={PANEL_LIMITS.right.max}
                direction={-1}
                onResize={(px) => setPanelSize("right", px)}
                onReset={resetTo("right")}
              />
              {activity({ onCollapse: () => setPanelOpen("right", false), className: "tile-enter-right shrink-0 overflow-hidden rounded-tile", style: { width: size.right } })}
            </>
          )}
        </div>
        {open.bottom && (
          <>
            <Gutter
              orientation="horizontal"
              label="Altezza del pannello ordini"
              value={size.bottom}
              min={PANEL_LIMITS.bottom.min}
              max={PANEL_LIMITS.bottom.max}
              direction={-1}
              onResize={(px) => setPanelSize("bottom", px)}
              onReset={resetTo("bottom")}
            />
            <OrdersDock
              selected={selected}
              onSelect={select}
              onHide={() => setPanelOpen("bottom", false)}
              className="tile-enter-bottom shrink-0 overflow-hidden rounded-tile"
              style={{ height: size.bottom }}
            />
          </>
        )}
      </div>
    </div>
  );
}
