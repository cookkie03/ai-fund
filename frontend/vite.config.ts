import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { officeFixtures } from "./dev/office-fixtures";
import { tickerFixtures } from "./dev/ticker-fixtures";

// The Runtime has no CORS: the browser reaches it through this same-origin proxy.
const runtimeUrl = process.env.COCKPIT_RUNTIME_URL ?? "http://127.0.0.1:8766";
const port = Number(process.env.COCKPIT_PORT ?? 5174);

export default defineConfig({
  // COCKPIT_OFFICE_FIXTURES=1: synthetic answers for the Ufficio reads the Runtime does not expose yet (dev server only).
  // COCKPIT_TICKER_FIXTURES=1 (or =dense, 40 tickers): synthetic ticker agents, dossiers and proposals (dev server only).
  plugins: [
    react(),
    tailwindcss(),
    ...(process.env.COCKPIT_TICKER_FIXTURES ? [tickerFixtures(runtimeUrl, process.env.COCKPIT_TICKER_FIXTURES)] : []),
    ...(process.env.COCKPIT_OFFICE_FIXTURES === "1" ? [officeFixtures()] : []),
  ],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
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
