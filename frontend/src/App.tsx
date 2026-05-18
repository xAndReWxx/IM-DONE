/* ============================================================
 * PhysioAI Pro V2 — App
 * ============================================================
 * Root component. Owns a single piece of state — which screen
 * we're on — and renders accordingly. No router needed; the
 * app has exactly two views.
 *
 * STATE FLOW
 *   landing → click "Begin session" → session
 *   session → click "EXIT" → landing
 *
 * The SessionScreen unmounts on exit, which tears down the
 * camera stream and WebSocket cleanly via the hooks' cleanup
 * functions.
 * ============================================================ */

import { useState } from "react";
import { LandingScreen } from "@/screens/LandingScreen";
import { SessionScreen } from "@/screens/SessionScreen";

type View = "landing" | "session";

export default function App() {
  const [view, setView] = useState<View>("landing");

  if (view === "session") {
    return <SessionScreen onBack={() => setView("landing")} />;
  }
  return <LandingScreen onStart={() => setView("session")} />;
}
