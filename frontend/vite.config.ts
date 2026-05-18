import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// ============================================================
// PhysioAI Pro V2 — Vite config
// ============================================================
// - React plugin for JSX/Fast Refresh
// - `@` alias → src/ (matches tsconfig paths)
// - Dev server binds 0.0.0.0 so mobile/tablet on the same LAN
//   can hit the dev server by IP
// - Proxies /ws/* and /health/* to the backend so the frontend
//   can use same-origin URLs (no CORS in dev)
// ============================================================
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      // HTTP health endpoints
      "/health": { target: "http://localhost:8000", changeOrigin: true },
      // WebSocket session endpoint — `ws: true` upgrades the proxy
      "/ws":     { target: "ws://localhost:8000", ws: true, changeOrigin: true },
    },
  },
});
