/* ============================================================
 * PhysioAI Pro V2 — App
 * ============================================================
 * Two views:
 *   landing → click "Start Scanning" → scanner
 *   scanner → click "EXIT" → landing
 *
 * Camera is lazy-loaded: only the ScannerScreen mounts the
 * camera hook. Landing is pure UI — zero device access.
 * ============================================================ */

import { useState } from "react";
import { LandingScreen } from "@/screens/LandingScreen";
import { SessionManager } from "@/screens/SessionManager";

type View = "landing" | "scanner";

export default function App() {
  const [view, setView] = useState<View>("landing");

  if (view === "scanner") {
    return <SessionManager onBack={() => setView("landing")} />;
  }
  return <LandingScreen onStart={() => setView("scanner")} />;
}
