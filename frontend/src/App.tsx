import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { MotionConfig } from "motion/react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BridgeProvider } from "@/features/bridge/state";
import { RuntimeProvider } from "@/lib/runtime/provider";
import { PendingPage } from "@/pages/pending";
import { AppShell } from "@/shell/app-shell";
import { NAV } from "@/shell/nav";
import { ShellStateProvider } from "@/shell/shell-state";

const TerminalPage = lazy(() => import("@/pages/terminal/terminal-page").then((m) => ({ default: m.TerminalPage })));
const PortafoglioPage = lazy(() => import("@/pages/portafoglio/portafoglio-page").then((m) => ({ default: m.PortafoglioPage })));
const UfficioPage = lazy(() => import("@/pages/ufficio/ufficio-page").then((m) => ({ default: m.UfficioPage })));

const ConfigurazioniPage = lazy(() => import("@/pages/configurazioni/configurazioni-page").then((m) => ({ default: m.ConfigurazioniPage })));
const NotiziePage = lazy(() => import("@/pages/notizie/notizie-page").then((m) => ({ default: m.NotiziePage })));
const AssistentePage = lazy(() => import("@/pages/assistente/assistente-page").then((m) => ({ default: m.AssistentePage })));
const TickerPage = lazy(() => import("@/pages/ticker/ticker-page").then((m) => ({ default: m.TickerPage })));

const pageFallback = <div className="flex-1 bg-ground" aria-busy />;

export function App() {
  return (
    <RuntimeProvider>
      <ShellStateProvider>
        <TooltipProvider>
          <MotionConfig reducedMotion="user">
            <BrowserRouter>
              <BridgeProvider>
            <AppShell>
              <Routes>
                {/* Home is the Assistente: the conversation with the Bridge. */}
                {["/", "/assistente"].map((path) => (
                  <Route
                    key={path}
                    path={path}
                    element={
                      <Suspense fallback={pageFallback}>
                        <AssistentePage />
                      </Suspense>
                    }
                  />
                ))}
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
                  path="/portafoglio"
                  element={
                    <Suspense fallback={pageFallback}>
                      <PortafoglioPage />
                    </Suspense>
                  }
                />
                {["/configurazioni", "/configurazioni/:section", "/configurazioni/:section/:agent"].map((path) => (
                  <Route
                    key={path}
                    path={path}
                    element={
                      <Suspense fallback={pageFallback}>
                        <ConfigurazioniPage />
                      </Suspense>
                    }
                  />
                ))}
                <Route
                  path="/notizie"
                  element={
                    <Suspense fallback={pageFallback}>
                      <NotiziePage />
                    </Suspense>
                  }
                />
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
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </AppShell>
              </BridgeProvider>
            </BrowserRouter>
            <Toaster position="bottom-right" />
          </MotionConfig>
        </TooltipProvider>
      </ShellStateProvider>
    </RuntimeProvider>
  );
}
