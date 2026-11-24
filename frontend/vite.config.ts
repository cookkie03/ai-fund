import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { officeFixtures } from "./dev/office-fixtures.ts";
import { portfolioFixtures } from "./dev/portfolio-fixtures.ts";
import { tickerFixtures } from "./dev/ticker-fixtures.ts";

// The Runtime has no CORS: the browser reaches it through this same-origin proxy.
const runtimeUrl = process.env.COCKPIT_RUNTIME_URL ?? "http://127.0.0.1:8766";
const port = Number(process.env.COCKPIT_PORT ?? 5174);

export default defineConfig({
  // COCKPIT_OFFICE_FIXTURES=1: synthetic answers for the Ufficio reads the Runtime does not expose yet (dev server only).
  // COCKPIT_PORTFOLIO_FIXTURES=1: the same for the Portafoglio reads and commands (contract in handoff-backend-portafoglio.md).
  // COCKPIT_TICKER_FIXTURES=1 (or =dense, 40 tickers): synthetic ticker agents, dossiers and proposals (dev server only).
  plugins: [
    react(),
    tailwindcss(),
    ...(process.env.COCKPIT_TICKER_FIXTURES ? [tickerFixtures(runtimeUrl, process.env.COCKPIT_TICKER_FIXTURES)] : []),
    ...(process.env.COCKPIT_OFFICE_FIXTURES === "1" ? [officeFixtures()] : []),
    ...(process.env.COCKPIT_PORTFOLIO_FIXTURES === "1" ? [portfolioFixtures()] : []),
  ],
  // Lets the page mark fixture figures as samples; always "" in a build.
  define: { "import.meta.env.VITE_PORTFOLIO_FIXTURES": JSON.stringify(process.env.COCKPIT_PORTFOLIO_FIXTURES === "1" ? "1" : "") },
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    host: "127.0.0.1",
    port,
    strictPort: true,
    proxy: {
      "/v1": {
        target: runtimeUrl,
        changeOrigin: false,
        // SSE: keep the stream open and unbuffered.
        configure: (proxy) => {
          proxy.on("proxyRes", (res) => {
            if (res.headers["content-type"]?.includes("text/event-stream")) {
              res.headers["cache-control"] = "no-cache";
              res.headers["x-accel-buffering"] = "no";
            }
          });
        },
      },
    },
  },
  preview: { host: "127.0.0.1", port },
});
