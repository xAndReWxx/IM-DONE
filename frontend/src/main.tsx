// ============================================================
// PhysioAI Pro V2 — React entry point
// ============================================================
// Mounts <App /> into #root. Strict mode is on for development
// only — it double-invokes effects which is great for catching
// bugs but can be removed if it causes camera double-init issues.
// ============================================================

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
