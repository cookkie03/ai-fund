import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Runtime has no CORS: the browser reaches it through this same-origin proxy.
const runtimeUrl = process.env.COCKPIT_RUNTIME_URL ?? "http://127.0.0.1:8766";
const port = Number(process.env.COCKPIT_PORT ?? 5174);

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
