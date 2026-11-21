import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { VariantSwitcher } from "@/components/variant-switcher";
import { TooltipProvider } from "@/components/ui/tooltip";
import { RuntimeProvider } from "@/lib/runtime/provider";
import { PendingPage } from "@/pages/pending";
import { AppShell } from "@/shell/app-shell";
import { NAV } from "@/shell/nav";
import { ShellStateProvider } from "@/shell/shell-state";

const TerminalPage = lazy(() => import("@/pages/terminal/terminal-page").then((m) => ({ default: m.TerminalPage })));

export function App() {
  return (
    <RuntimeProvider>
      <ShellStateProvider>
        <TooltipProvider>
          <BrowserRouter>
            <AppShell>
              <Routes>
                {/* Home is the Assistente; until it is built the cockpit opens on the Terminale. */}
                <Route path="/" element={<Navigate to="/terminale" replace />} />
                <Route
                  path="/terminale"
                  element={
                    <Suspense fallback={<div className="flex-1 bg-ground" aria-busy />}>
                      <TerminalPage />
                    </Suspense>
                  }
                />
                {NAV.filter((n) => !n.built).map((n) => (
                  <Route key={n.path} path={n.path} element={<PendingPage item={n} />} />
                ))}
                <Route path="*" element={<Navigate to="/terminale" replace />} />
              </Routes>
            </AppShell>
          </BrowserRouter>
          <VariantSwitcher />
            <Toaster position="bottom-right" />
        </TooltipProvider>
      </ShellStateProvider>
    </RuntimeProvider>
  );
}
