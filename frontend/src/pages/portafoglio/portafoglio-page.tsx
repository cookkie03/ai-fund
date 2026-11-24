import { useEffect, useState } from "react";
import { PanelTab, PanelTabContent, PanelTabs, PanelTabsList } from "@/components/panel-tabs";
import { usePositions, useRiskLimits, useSummary } from "@/features/portfolio/hooks";
import type { Period } from "@/features/portfolio/types";
import { orderBucket } from "@/lib/orders";
import { useOrders } from "@/lib/runtime/hooks";
import { useNow, useRuntime } from "@/lib/runtime/provider";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { useShell } from "@/shell/shell-state";
import { AllocationTile } from "./allocation";
import { EquityChart } from "./equity-chart";
import { OperationsPanel } from "./operations";
import { PerformancePanel } from "./performance";
import { PositionsPanel } from "./positions";
import { RiskPanel } from "./risk";
import { Freshness, HaltBanner, SummaryBand } from "./summary";

type Tab = "positions" | "operations" | "performance" | "risk";
const TAB_KEY = "cockpit.portafoglio.tab";

const isTab = (t: string | null): t is Tab => t === "positions" || t === "operations" || t === "performance" || t === "risk";

function loadTab(): Tab {
  // A link can open a tab directly (Configurazioni → Limiti di rischio: /portafoglio?tab=risk).
  const fromUrl = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("tab");
  if (isTab(fromUrl)) return fromUrl;
  try {
    const t = localStorage.getItem(TAB_KEY);
    if (isTab(t)) return t;
  } catch {
    /* storage unavailable */
  }
  return "positions";
}

/**
 * The account read like a manager's statement: overview on top (equity, today, curve against SPY, allocation
 * against its limits), then Posizioni, Operazioni, Performance and Rischio e vincoli as tabs.
 */
export function PortafoglioPage() {
  const wide = useMediaQuery("(min-width: 768px)");
  const roomy = useMediaQuery("(min-width: 1180px)");
  const { halted } = useShell();
  const { target, health } = useRuntime();
  const now = useNow(15_000);
  const summary = useSummary();
  const positions = usePositions();
  const risk = useRiskLimits();
  const orders = useOrders();
  const [period, setPeriod] = useState<Period>("3M");
  const [tab, setTabState] = useState<Tab>(loadTab);
  const setTab = (t: string) => {
    setTabState(t as Tab);
    try {
      localStorage.setItem(TAB_KEY, t);
    } catch {
      /* storage unavailable */
    }
  };

  useEffect(() => {
    document.title = "Portafoglio";
  }, []);

  const s = summary.data && summary.data.source !== "unavailable" ? summary.data.data : null;
  const pos = positions.data && positions.data.source !== "unavailable" ? positions.data.data : null;
  const limits = risk.data && risk.data.source !== "unavailable" ? risk.data.data : null;
  const pending = (orders.data ?? []).filter((o) => orderBucket(o) === "pending").length;
  const flagged = limits?.usage.filter((u) => u.status !== "ok") ?? [];
  const breach = flagged.some((u) => u.status === "breach");

  const header = (
    <div className="flex shrink-0 flex-wrap items-end gap-x-4 gap-y-1 px-2 pb-3 pt-1 md:px-1">
      <div className="min-w-0">
        <h1 className="text-base font-semibold tracking-[-0.01em] text-fg">Portafoglio</h1>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-fg-subtle">
          <span>
            Conto <span className="text-fg-muted">{health?.account_label ?? target.label ?? target.id}</span>
          </span>
          {import.meta.env.VITE_PORTFOLIO_FIXTURES === "1" && (
            <span data-sample className="rounded-tag bg-warn-soft px-1.5 py-px font-medium text-warn" title="COCKPIT_PORTFOLIO_FIXTURES=1: numeri sintetici del dev server, non il conto">
              Dati di esempio
            </span>
          )}
          <Freshness summary={s} now={now} />
          {health && !health.broker_stream_connected && health.broker_configured && <span className="text-warn">Stream del broker disconnesso</span>}
        </p>
      </div>
    </div>
  );

  const tabs = (
    <PanelTabs value={tab} onValueChange={setTab} className="flex min-w-0 flex-col">
      <PanelTabsList className={cn(!wide && "px-1.5 [&_[role=tablist]]:flex [&_[role=tablist]]:w-full [&_[role=tab]]:flex-1 [&_[role=tab]]:justify-center [&_[role=tab]]:px-1.5")}>
        <PanelTab value="positions" count={pos?.length}>
          Posizioni
        </PanelTab>
        <PanelTab value="operations" count={pending} tone="warn">
          {wide ? "Operazioni" : "Ordini"}
        </PanelTab>
        <PanelTab value="performance">Performance</PanelTab>
        <PanelTab value="risk" count={flagged.length} tone="warn" className={cn(breach && "[&>span]:bg-down-soft [&>span]:text-down")}>
          {wide ? "Rischio e vincoli" : "Rischio"}
        </PanelTab>
      </PanelTabsList>
      <PanelTabContent value="positions" className="tab-in">
        <PositionsPanel q={positions} limits={limits} equity={s?.equity ?? null} cash={s?.cash ?? null} mobile={!wide} />
      </PanelTabContent>
      <PanelTabContent value="operations" className="tab-in">
        <OperationsPanel limits={limits} mobile={!wide} />
      </PanelTabContent>
      <PanelTabContent value="performance" className="tab-in">
        <PerformancePanel period={period} onPeriod={setPeriod} mobile={!wide} />
      </PanelTabContent>
      <PanelTabContent value="risk" className="tab-in">
        <RiskPanel q={risk} mobile={!wide} before={!wide ? <AllocationTile className="mx-1.5 mb-2 border border-border/50 bg-card" /> : undefined} />
      </PanelTabContent>
    </PanelTabs>
  );

  if (!wide) {
    return (
      <div data-region="workspace" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto pb-2">
        {header}
        <div className="space-y-2.5 px-2">
          {halted && <HaltBanner />}
          <SummaryBand q={summary} positions={pos} limits={limits} compact />
          <EquityChart period={period} onPeriod={setPeriod} height={220} compact />
          <section aria-label="Sezioni del portafoglio" className="rounded-tile bg-ground">
            {tabs}
          </section>
        </div>
      </div>
    );
  }

  return (
    <div data-region="workspace" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto pb-2.5 pr-2.5">
      {header}
      <div className="space-y-2.5">
        {halted && <HaltBanner />}
        <SummaryBand q={summary} positions={pos} limits={limits} />
        <div className={cn("grid gap-2.5", roomy ? "grid-cols-[minmax(0,1fr)_400px]" : "grid-cols-1")}>
          <EquityChart period={period} onPeriod={setPeriod} height={roomy ? 280 : 260} />
          <AllocationTile className={cn(!roomy && "max-h-[420px]")} />
        </div>
        <section aria-label="Sezioni del portafoglio" data-region="tabs" className="min-w-0 rounded-tile bg-ground">
          {tabs}
        </section>
      </div>
    </div>
  );
}
