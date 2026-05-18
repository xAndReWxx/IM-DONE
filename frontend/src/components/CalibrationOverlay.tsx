/* ============================================================
 * PhysioAI Pro V2 — CalibrationOverlay (Front-Only)
 * ============================================================
 * Renders the AI-guided calibration UI over the camera feed.
 * Simplified for front-only scanning:
 *   • Readiness score arc
 *   • Stability meter
 *   • Confidence grade
 *   • Guidance messages
 *   • Scan captured flash
 *   • Complete / processing states
 *
 * No orientation arrows, no multi-phase progress, no
 * left/right/back prompts.
 * ============================================================ */

import { useEffect, useRef } from "react";
import type {
  CalibrationUpdateMessage,
  CalibrationState,
} from "@/lib/websocket-types";
import { useVoiceGuidance } from "@/hooks/useVoiceGuidance";
import "./CalibrationOverlay.css";

type Props = {
  calibration: CalibrationUpdateMessage;
  onStop: () => void;
};

const STATE_ICONS: Partial<Record<CalibrationState, string>> = {
  initializing: "⚙",
  body_detection: "👤",
  body_validation: "📐",
  front_scan: "🎯",
  processing: "🧠",
  complete: "✓",
  error: "⚠",
};

export function CalibrationOverlay({ calibration, onStop }: Props) {
  const { speak } = useVoiceGuidance();
  const lastVoiceRef = useRef<string | null>(null);

  // Speak voice guidance when it changes.
  useEffect(() => {
    if (
      calibration.voice_message &&
      calibration.voice_message !== lastVoiceRef.current
    ) {
      lastVoiceRef.current = calibration.voice_message;
      speak(calibration.voice_message);
    }
  }, [calibration.voice_message, speak]);

  const isScanning = calibration.state === "front_scan";
  const readinessPercent = Math.round(calibration.readiness_score * 100);

  const stateColor =
    calibration.state === "error"
      ? "var(--c-bad)"
      : calibration.state === "complete"
        ? "var(--c-good)"
        : isScanning
          ? "var(--c-signal)"
          : "var(--c-text-dim)";

  return (
    <div className="cal-overlay" data-state={calibration.state}>
      {/* ── Top: State header ── */}
      <div className="cal-header">
        <div className="cal-header__left">
          <span className="cal-header__icon" style={{ color: stateColor }}>
            {STATE_ICONS[calibration.state] ?? "●"}
          </span>
          <span className="cal-header__state label">
            {calibration.state_name.toUpperCase()}
          </span>
        </div>
        <button
          type="button"
          className="cal-header__stop label"
          onClick={onStop}
        >
          CANCEL
        </button>
      </div>

      {/* ── Center: Readiness arc ── */}
      {(calibration.state === "body_validation" || isScanning) && (
        <div className="cal-center">
          <div className="cal-readiness">
            <svg viewBox="0 0 120 120" className="cal-readiness__svg">
              <circle
                cx="60" cy="60" r="52"
                fill="none"
                stroke="var(--c-line-strong)"
                strokeWidth="4"
              />
              <circle
                cx="60" cy="60" r="52"
                fill="none"
                stroke={readinessPercent >= 100 ? "var(--c-good)" : "var(--c-signal)"}
                strokeWidth="4"
                strokeDasharray={`${2 * Math.PI * 52}`}
                strokeDashoffset={`${2 * Math.PI * 52 * (1 - calibration.readiness_score)}`}
                strokeLinecap="round"
                className="cal-readiness__arc"
              />
            </svg>
            <span className="cal-readiness__value mono">
              {readinessPercent}%
            </span>
          </div>
        </div>
      )}

      {/* ── Bottom panel: Guidance + metrics ── */}
      <div className="cal-bottom">
        {/* Guidance messages */}
        <div className="cal-guidance">
          {calibration.guidance_messages.slice(0, 3).map((msg, i) => (
            <p
              key={`${msg}-${i}`}
              className={`cal-guidance__msg ${i === 0 ? "cal-guidance__msg--primary" : ""}`}
            >
              {msg}
            </p>
          ))}
        </div>

        {/* Metrics bar */}
        {(calibration.state === "body_validation" || isScanning) && (
          <div className="cal-metrics">
            {/* Stability */}
            {calibration.stability && (
              <div className="cal-metric">
                <span className="cal-metric__label label">STABILITY</span>
                <div className="cal-metric__bar">
                  <div
                    className="cal-metric__fill"
                    style={{
                      width: `${calibration.stability.stability_score * 100}%`,
                      background: calibration.stability.stability_confirmed
                        ? "var(--c-good)"
                        : calibration.stability.is_stable
                          ? "var(--c-signal)"
                          : "var(--c-bad)",
                    }}
                  />
                </div>
              </div>
            )}
            {/* Confidence */}
            {calibration.confidence && (
              <div className="cal-metric">
                <span className="cal-metric__label label">CONFIDENCE</span>
                <div className="cal-metric__bar">
                  <div
                    className="cal-metric__fill"
                    style={{
                      width: `${calibration.confidence.overall_confidence * 100}%`,
                      background:
                        calibration.confidence.grade === "good"
                          ? "var(--c-good)"
                          : calibration.confidence.grade === "fair"
                            ? "var(--c-signal)"
                            : "var(--c-bad)",
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Scan captured flash ── */}
      {calibration.scan_captured && (
        <div className="cal-captured-flash">
          <span className="cal-captured-flash__icon">✓</span>
          <span className="cal-captured-flash__text label">SCAN CAPTURED</span>
        </div>
      )}

      {/* ── Complete state ── */}
      {calibration.state === "complete" && (
        <div className="cal-complete">
          <span className="cal-complete__icon">✓</span>
          <span className="cal-complete__text">Scan Complete</span>
          <span className="cal-complete__sub label">
            Posture analysis ready
          </span>
        </div>
      )}

      {/* ── Processing state ── */}
      {calibration.state === "processing" && (
        <div className="cal-processing">
          <div className="cal-processing__spinner" />
          <span className="cal-processing__text label">
            ANALYZING POSTURE DATA
          </span>
        </div>
      )}
    </div>
  );
}
