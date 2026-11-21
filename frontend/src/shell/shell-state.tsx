import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useRuntime } from "@/lib/runtime/provider";

type ShellState = {
  bridgeOpen: boolean;
  setBridgeOpen: (open: boolean) => void;
  /** Open the Bridge with "@agent " typed in the composer. */
  messageAgent: (agent: string, context?: string) => void;
  composerSeed: { text: string; nonce: number } | null;
  /** Writes are refused while the Runtime is unreachable. */
  writable: boolean;
  halted: boolean;
};

const Ctx = createContext<ShellState | null>(null);

export function ShellStateProvider({ children }: { children: ReactNode }) {
  const { connection, health } = useRuntime();
  const [bridgeOpen, setBridgeOpen] = useState(() => typeof window !== "undefined" && window.innerWidth >= 1600);
  const [composerSeed, setComposerSeed] = useState<ShellState["composerSeed"]>(null);
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
    }),
    [bridgeOpen, composerSeed, connection.reachable, health?.halted],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useShell(): ShellState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useShell outside ShellStateProvider");
  return ctx;
}
