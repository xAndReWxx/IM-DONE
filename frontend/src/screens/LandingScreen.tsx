/* ============================================================
 * PhysioAI Pro V2 — LandingScreen
 * ============================================================
 * What the user sees first. Layout, top to bottom:
 *
 *   [ TOP STATUS BAR ]    instrument-style header
 *   [ TWO ROBOTIC EYES ]  left + right, autonomous saccadic gaze
 *   [ HERO TITLE ]        large display type
 *   [ START SESSION ]     primary action
 *   [ TELEMETRY ROW ]     mono ticker at bottom
 *
 * The left eye drives the primary gaze from useEyeFocus().
 * The right eye receives a 200ms-delayed copy of the same
 * values, simulating slightly desynchronised bilateral vision.
 * ============================================================ */

import { useEffect, useRef, useState } from "react";
import { RoboticEye } from "@/components/RoboticEye";
import { useEyeFocus } from "@/hooks/useEyeFocus";
import "./LandingScreen.css";

type Props = {
  onStart: () => void;
};

export function LandingScreen({ onStart }: Props) {
  // Live clock for the top status bar (HH:MM:SS, mono).
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const hms = now.toTimeString().slice(0, 8);

  // Primary autonomous gaze (left eye uses this directly).
  const primaryGaze = useEyeFocus();

  // Secondary gaze: 200ms-delayed copy for the right eye.
  const [secondaryGaze, setSecondaryGaze] = useState({ x: 0, y: 0 });
  const primaryRef = useRef(primaryGaze);
  primaryRef.current = primaryGaze;

  useEffect(() => {
    const id = setTimeout(() => {
      setSecondaryGaze({ ...primaryRef.current });
    }, 200);
    return () => clearTimeout(id);
  // Re-fire the 200ms delay every time primaryGaze updates.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [primaryGaze.x, primaryGaze.y]);

  return (
    <main className="landing">
      {/* Background: ultra-subtle dotted grid for "instrument paper" depth */}
      <div className="landing__grid" aria-hidden />
      <div className="landing__vignette" aria-hidden />

      {/* ── Top status bar ── */}
      <header className="landing__topbar">
        <div className="landing__topbar-left">
          <span className="landing__dot" aria-hidden />
          <span className="label">SYS · ONLINE</span>
        </div>
        <div className="landing__brand">
          <span className="label landing__brand-name">PhysioAI</span>
          <span className="label landing__brand-version">V2.0</span>
        </div>
        <div className="landing__topbar-right mono">
          <span>{hms}</span>
        </div>
      </header>

      {/* ── Eyes centerpiece ── */}
      <div className="landing__stage">
        <RoboticEye side="left"  gazeX={primaryGaze.x}   gazeY={primaryGaze.y} />
        <RoboticEye side="right" gazeX={secondaryGaze.x} gazeY={secondaryGaze.y} />

        {/* Crosshair markers — corner brackets framing the eyes */}
        <div className="landing__bracket landing__bracket--tl" aria-hidden />
        <div className="landing__bracket landing__bracket--tr" aria-hidden />
        <div className="landing__bracket landing__bracket--bl" aria-hidden />
        <div className="landing__bracket landing__bracket--br" aria-hidden />
      </div>

      {/* ── Hero copy + CTA ── */}
      <section className="landing__hero">
        <p className="label landing__hero-eyebrow">REALTIME · POSTURE · COACH</p>
        <h1 className="landing__title">
          stand <em>tall</em>.<br />
          let the machine watch.
        </h1>
        <p className="landing__subtitle">
          Open your camera. PhysioAI analyzes your posture frame by frame
          and coaches you back to alignment, in Arabic, offline.
        </p>

        <button
          type="button"
          className="landing__cta"
          onClick={onStart}
        >
          <span className="landing__cta-label">Begin session</span>
          <span className="landing__cta-arrow" aria-hidden>→</span>
        </button>
      </section>

      {/* ── Bottom telemetry strip ── */}
      <footer className="landing__telemetry">
        <Telemetry label="MODE"      value="OFFLINE" />
        <Telemetry label="CAMERA"    value="STANDBY" />
        <Telemetry label="PIPELINE"  value="MEDIAPIPE × FASTAPI" />
        <Telemetry label="LATENCY"   value="< 80 MS" />
      </footer>
    </main>
  );
}

function Telemetry({ label, value }: { label: string; value: string }) {
  return (
    <div className="landing__telem-item">
      <span className="label landing__telem-label">{label}</span>
      <span className="mono landing__telem-value">{value}</span>
    </div>
  );
}
