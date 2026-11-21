import { CloudOff, OctagonPause, RotateCw } from "lucide-react";
import type { ReactNode } from "react";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { fmtAge } from "@/lib/format";
import { queryClient, useNow, useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { useMediaQuery } from "@/lib/use-media-query";
import { BridgePanel } from "./bridge";
import { BottomNav, Rail } from "./rail";
import { useShell } from "./shell-state";
import { TopBar } from "./top-bar";

function UnreachableBanner() {
  const { connection } = useRuntime();
  const now = useNow(1000);
  return (
    <div role="alert" data-region="banner" className="mx-2.5 mb-2.5 flex shrink-0 items-center gap-3 rounded-control bg-[oklch(0.2_0.035_22)] px-3 py-2 text-xs shadow-[inset_0_0_0_1px_oklch(0.67_0.195_20/0.3)] md:ml-0">
      <CloudOff className="size-4 shrink-0 text-down" />
      <span className="font-medium text-fg">Runtime irraggiungibile.</span>
      <span className="min-w-0 truncate text-fg-muted">
        {connection.lastSyncAt
          ? `Quello che vedi è fermo a ${fmtAge(connection.lastSyncAt, now)} fa e i comandi sono sospesi.`
          : "Nessun dato caricato: verifica che il Runtime sia avviato e raggiungibile da questo indirizzo."}{" "}
        Nuovo tentativo ogni 10 s.
      </span>
      <button
        type="button"
        onClick={() => queryClient.invalidateQueries({ queryKey: ["health"] })}
        className="ml-auto inline-flex h-6 shrink-0 items-center gap-1 rounded-item px-2 text-fg-muted hover:bg-hover hover:text-fg"
      >
        <RotateCw className="size-3.5" /> Riprova ora
      </button>
    </div>
  );
}

function HaltBanner() {
  const { writable } = useShell();
  return (
    <div role="status" data-region="banner" className="mx-2.5 mb-2.5 flex shrink-0 items-center gap-3 rounded-control bg-[oklch(0.205_0.045_22)] px-3 py-1.5 text-xs shadow-[inset_0_0_0_1px_oklch(0.58_0.2_25/0.4)] md:ml-0">
      <OctagonPause className="size-4 shrink-0 text-down" />
      <span className="font-medium text-fg">Halt attivo: nessun ordine viene inviato al broker.</span>
      <span className="hidden min-w-0 truncate text-fg-muted md:inline">Gli agenti continuano ad analizzare. Approvazioni sospese finché non riprendi.</span>
      {!writable && <span className="ml-auto text-fg-subtle">Comandi sospesi</span>}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { connection } = useRuntime();
  const { bridgeOpen, setBridgeOpen, halted } = useShell();
  const wide = useMediaQuery("(min-width: 1280px)");
  const down = !connection.booting && !connection.reachable;

  return (
    <div data-region="shell" className="flex h-dvh w-full overflow-hidden bg-desk">
      <Rail />
      <div data-region="column" className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        {down && <UnreachableBanner />}
        {halted && !down && <HaltBanner />}
        <main data-region="canvas" className={cn("flex min-h-0 flex-1 transition-[filter,opacity] duration-300", down && "opacity-70 saturate-[0.35]")} aria-busy={connection.booting}>
          {children}
        </main>
        <BottomNav />
      </div>
      {wide ? (
        bridgeOpen && (
          <div data-region="bridge" className="tile-enter-right w-[340px] shrink-0 py-2.5 pr-2.5">
            <div className="h-full overflow-hidden rounded-tile bg-ground">
              <BridgePanel onClose={() => setBridgeOpen(false)} />
            </div>
          </div>
        )
      ) : (
        <Sheet open={bridgeOpen} onOpenChange={setBridgeOpen}>
          <SheetContent side="right" className="w-full max-w-[400px] gap-0 rounded-l-tile border-0 bg-ground p-0 [&>button]:hidden">
            <SheetTitle className="sr-only">Bridge</SheetTitle>
            <BridgePanel onClose={() => setBridgeOpen(false)} />
          </SheetContent>
        </Sheet>
      )}
    </div>
  );
}
