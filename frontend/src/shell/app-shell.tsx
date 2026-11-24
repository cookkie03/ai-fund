import { CloudOff, OctagonPause, RotateCw } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { tileTransition } from "@/lib/motion";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { fmtAge } from "@/lib/format";
import { queryClient, useNow, useRuntime } from "@/lib/runtime/provider";
import { cn } from "@/lib/utils";
import { useMediaQuery } from "@/lib/use-media-query";
import { BridgePanel } from "./bridge";
import { AppSidebar, BottomNav } from "./rail";
import { useShell } from "./shell-state";
import { TopBar } from "./top-bar";

function UnreachableBanner() {
  const { connection } = useRuntime();
  const now = useNow(1000);
  return (
    <div
      role="alert"
      data-region="banner"
      className="mx-2.5 mb-2.5 flex shrink-0 items-center gap-3 rounded-control border border-border bg-card px-3 py-2 text-xs shadow-xs md:ml-0"
    >
      <Badge variant="destructive" className="h-5 px-1.5 gap-1">
        <CloudOff className="size-3" />
        Offline
      </Badge>
      <span className="font-medium text-fg">Runtime irraggiungibile.</span>
      <span className="min-w-0 truncate text-fg-muted">
        {connection.lastSyncAt
          ? `Dati fermi a ${fmtAge(connection.lastSyncAt, now)} fa. Comandi sospesi.`
          : "Nessun dato caricato: verifica che il Runtime sia avviato."}{" "}
        Nuovo tentativo ogni 10 s.
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => queryClient.invalidateQueries({ queryKey: ["health"] })}
        className="ml-auto h-6 shrink-0 gap-1 px-2 text-fg-muted hover:text-fg"
      >
        <RotateCw className="size-3" /> Riprova ora
      </Button>
    </div>
  );
}

function HaltBanner() {
  const { writable } = useShell();
  return (
    <div
      role="status"
      data-region="banner"
      className="mx-2.5 mb-2.5 flex shrink-0 items-center gap-3 rounded-control border border-border bg-card px-3 py-1.5 text-xs shadow-xs md:ml-0"
    >
      <Badge variant="destructive" className="h-5 px-1.5 gap-1">
        <OctagonPause className="size-3" />
        Halt
      </Badge>
      <span className="font-medium text-fg">Trading bloccato: nessun ordine al broker.</span>
      <span className="hidden min-w-0 truncate text-fg-muted md:inline">
        Gli agenti continuano l'analisi; ordini e approvazioni sono in attesa.
      </span>
      {!writable && <Badge variant="outline" className="ml-auto text-fg-subtle">Sola lettura</Badge>}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { connection } = useRuntime();
  const { bridgeOpen, setBridgeOpen, halted } = useShell();
  const wide = useMediaQuery("(min-width: 1280px)");
  const down = !connection.booting && !connection.reachable;

  return (
    <SidebarProvider defaultOpen={false}>
      <div data-region="shell" className="flex h-dvh w-full overflow-hidden bg-desk">
        <AppSidebar />
        <SidebarInset className="flex min-w-0 flex-1 flex-col bg-desk">
          <TopBar />
          {down && <UnreachableBanner />}
          {halted && !down && <HaltBanner />}
          <main
            data-region="canvas"
            className={cn(
              "flex min-h-0 flex-1 transition-[filter,opacity] duration-300",
              down && "opacity-70 saturate-[0.35]"
            )}
            aria-busy={connection.booting}
          >
            {children}
          </main>
          <BottomNav />
        </SidebarInset>
        {wide ? (
          <AnimatePresence>
            {bridgeOpen && (
              <motion.div
                key="bridge"
                data-region="bridge"
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                transition={tileTransition}
                className="w-[340px] shrink-0 py-2.5 pr-2.5"
              >
                <div className="h-full overflow-hidden rounded-tile border border-line-strong/60 bg-ground shadow-sm">
                  <BridgePanel onClose={() => setBridgeOpen(false)} />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        ) : (
          <Sheet open={bridgeOpen} onOpenChange={setBridgeOpen}>
            <SheetContent side="right" className="w-full max-w-[400px] gap-0 rounded-l-tile border-0 bg-ground p-0 [&>button]:hidden">
              <SheetTitle className="sr-only">Bridge</SheetTitle>
              <BridgePanel onClose={() => setBridgeOpen(false)} />
            </SheetContent>
          </Sheet>
        )}
      </div>
    </SidebarProvider>
  );
}
