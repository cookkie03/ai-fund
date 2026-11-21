import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRuntime } from "@/lib/runtime/provider";

/** The page's three dockable areas, named like VS Code: side bar, secondary side bar, panel. */
export type PanelId = "left" | "right" | "bottom";

type Layout = {
  open: Record<PanelId, boolean>;
  size: Record<PanelId, number>;
};

export const PANEL_LIMITS: Record<PanelId, { min: number; max: number; initial: number }> = {
  left: { min: 220, max: 420, initial: 272 },
  right: { min: 264, max: 460, initial: 312 },
  bottom: { min: 132, max: 520, initial: 240 },
};

export const PANEL_SHORTCUT: Record<PanelId, string> = {
  left: "Ctrl/⌘ B",
  bottom: "Ctrl/⌘ J",
  right: "Ctrl/⌘ Alt B",
};

const LAYOUT_KEY = "cockpit.layout";

function loadLayout(): Layout {
  const fallback: Layout = {
    // Below 1280 px the chart needs the room: the activity tile starts hidden (Ctrl/⌘ Alt B brings it back).
    open: { left: true, right: typeof window === "undefined" || window.innerWidth >= 1280, bottom: true },
    size: { left: PANEL_LIMITS.left.initial, right: PANEL_LIMITS.right.initial, bottom: PANEL_LIMITS.bottom.initial },
  };
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<Layout>;
    return { open: { ...fallback.open, ...parsed.open }, size: { ...fallback.size, ...parsed.size } };
  } catch {
    return fallback;
  }
}

const clamp = (id: PanelId, v: number) => Math.round(Math.min(PANEL_LIMITS[id].max, Math.max(PANEL_LIMITS[id].min, v)));

type ShellState = {
  bridgeOpen: boolean;
  setBridgeOpen: (open: boolean) => void;
  /** Open the Bridge with "@agent " typed in the composer. */
  messageAgent: (agent: string, context?: string) => void;
  composerSeed: { text: string; nonce: number } | null;
  /** Writes are refused while the Runtime is unreachable. */
  writable: boolean;
  halted: boolean;
  layout: Layout;
  setPanelOpen: (id: PanelId, open: boolean) => void;
  togglePanel: (id: PanelId) => void;
  setPanelSize: (id: PanelId, px: number) => void;
};

const Ctx = createContext<ShellState | null>(null);

export function ShellStateProvider({ children }: { children: ReactNode }) {
  const { connection, health } = useRuntime();
  const [bridgeOpen, setBridgeOpen] = useState(() => typeof window !== "undefined" && window.innerWidth >= 1600);
  const [composerSeed, setComposerSeed] = useState<ShellState["composerSeed"]>(null);
  const [layout, setLayout] = useState<Layout>(loadLayout);

  useEffect(() => {
    try {
      localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout));
    } catch {
      /* storage unavailable: the layout lasts for this visit */
    }
  }, [layout]);

  const setPanelOpen = useCallback((id: PanelId, open: boolean) => setLayout((l) => ({ ...l, open: { ...l.open, [id]: open } })), []);
  const togglePanel = useCallback((id: PanelId) => setLayout((l) => ({ ...l, open: { ...l.open, [id]: !l.open[id] } })), []);
  const setPanelSize = useCallback((id: PanelId, px: number) => setLayout((l) => ({ ...l, size: { ...l.size, [id]: clamp(id, px) } })), []);

  // VS Code bindings: Ctrl/⌘+B side bar, Ctrl/⌘+J panel, Ctrl/⌘+Alt+B secondary side bar.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.shiftKey) return;
      const key = e.code === "KeyB" ? "b" : e.code === "KeyJ" ? "j" : null;
      if (!key) return;
      e.preventDefault();
      togglePanel(key === "j" ? "bottom" : e.altKey ? "right" : "left");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePanel]);

  const value = useMemo<ShellState>(
    () => ({
      bridgeOpen,
      setBridgeOpen,
      composerSeed,
      messageAgent: (agent, context) => {
        setComposerSeed({ text: `@${agent} ${context ? context + " " : ""}`, nonce: Date.now() });
        setBridgeOpen(true);
      },
      writable: connection.reachable,
      halted: !!health?.halted,
      layout,
      setPanelOpen,
      togglePanel,
      setPanelSize,
    }),
    [bridgeOpen, composerSeed, connection.reachable, health?.halted, layout, setPanelOpen, togglePanel, setPanelSize],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useShell(): ShellState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useShell outside ShellStateProvider");
  return ctx;
}
