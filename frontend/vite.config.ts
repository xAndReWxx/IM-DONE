import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import basicSsl from "@vitejs/plugin-basic-ssl";
import path from "path";

// ============================================================
// PhysioAI Pro V2 — Vite config
// ============================================================
// - React plugin for JSX/Fast Refresh
// - `@` alias → src/ (matches tsconfig paths)
// - basicSsl plugin generates a self-signed certificate so
//   mobile/tablet browsers on the LAN can access getUserMedia
//   (browsers block camera on plain HTTP non-localhost origins)
// - Dev server binds 0.0.0.0 so mobile/tablet on the same LAN
//   can hit the dev server by IP
// - Proxies /ws/* and /health/* to the backend so the frontend
//   can use same-origin URLs (no CORS in dev)
//
// TABLET ACCESS:
//   1. Start the dev server: npm run dev
//   2. Open https://<LAPTOP_IP>:5173 on the tablet
//   3. Accept the self-signed certificate warning
//   4. Camera + WebSocket will work over the secure context
// ============================================================
export default defineConfig({
  plugins: [
    react(),
    basicSsl({
      name: "physioai-dev",
    }),
  ],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    // HTTPS is enabled by the basicSsl plugin above.
    // This creates a self-signed cert that browsers will warn
    // about once — accept it and camera access works.
    proxy: {
      // HTTP health endpoints
      "/health": { target: "http://localhost:8000", changeOrigin: true },
      // WebSocket session endpoint — `ws: true` upgrades the proxy.
      // Note: even though the frontend is served over HTTPS, the
      // proxy connection to the backend stays HTTP/WS (local only).
      "/ws": { target: "ws://localhost:8000", ws: true, changeOrigin: true },
    },
  },
});
