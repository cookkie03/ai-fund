import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { RuntimeProvider } from "@/lib/runtime/provider";
import { PendingPage } from "@/pages/pending";
import { AppShell } from "@/shell/app-shell";
import { NAV } from "@/shell/nav";
import { ShellStateProvider } from "@/shell/shell-state";

const TerminalPage = lazy(() => import("@/pages/terminal/terminal-page").then((m) => ({ default: m.TerminalPage })));
const UfficioPage = lazy(() => import("@/pages/ufficio/ufficio-page").then((m) => ({ default: m.UfficioPage })));

const TickerPage = lazy(() => import("@/pages/ticker/ticker-page").then((m) => ({ default: m.TickerPage })));

const pageFallback = <div className="flex-1 bg-ground" aria-busy />;

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
                    <Suspense fallback={pageFallback}>
                      <TerminalPage />
                    </Suspense>
                  }
                />
                {["/ufficio", "/ufficio/:agent"].map((path) => (
                  <Route
                    key={path}
                    path={path}
                    element={
                      <Suspense fallback={pageFallback}>
                        <UfficioPage />
                      </Suspense>
                    }
                  />
                ))}
                <Route
                  path="/ticker/:symbol"
                  element={
                    <Suspense fallback={pageFallback}>
                      <TickerPage />
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
            <Toaster position="bottom-right" />
        </TooltipProvider>
      </ShellStateProvider>
    </RuntimeProvider>
  );
}
