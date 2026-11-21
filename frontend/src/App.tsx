import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { RuntimeProvider } from "@/lib/runtime/provider";
import { PendingPage } from "@/pages/pending";
import { TerminalPage } from "@/pages/terminal/terminal-page";
import { AppShell } from "@/shell/app-shell";
import { NAV } from "@/shell/nav";
import { ShellStateProvider } from "@/shell/shell-state";

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
                <Route path="/terminale" element={<TerminalPage />} />
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
