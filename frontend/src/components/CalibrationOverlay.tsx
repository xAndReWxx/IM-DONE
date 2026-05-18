/* ============================================================
 * PhysioAI Pro V2 — CalibrationOverlay
 * ============================================================
 * Renders the AI-guided calibration UI over the camera feed.
 * Shows:
 *   • Current calibration state and guidance
 *   • Body alignment guide (crosshair + centering indicator)
 *   • Orientation indicator with progress ring
 *   • Stability meter
 *   • Confidence grade
 *   • Scan progress tracker (4 phases)
 *   • Animated transitions between states
 *   • Readiness score arc
 *
 * This component replaces the old timer-based scan card.
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

const PHASE_LABELS: Record<string, string> = {
  front: "Front",
  right: "Right",
  left: "Left",
  back: "Back",
};

const STATE_ICONS: Partial<Record<CalibrationState, string>> = {
  initializing: "⚙",
  body_detection: "👤",
  body_validation: "📐",
  front_scan: "🎯",
  right_scan: "🎯",
  left_scan: "🎯",
  back_scan: "🎯",
  processing: "🧠",
  complete: "✓",
  error: "⚠",
};

const ORIENTATION_ARROWS: Record<string, string> = {
  front_facing: "↑",
  right_profile: "→",
  left_profile: "←",
  back_view: "↓",
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

  const isScanning = [
    "front_scan",
    "right_scan",
    "left_scan",
    "back_scan",
  ].includes(calibration.state);

  const readinessPercent = Math.round(calibration.readiness_score * 100);
  const completedCount = calibration.completed_phases.length;

  // Determine color based on state.
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
          <div className="cal-header__info">
            <span className="cal-header__state label">
              {calibration.state_name.toUpperCase()}
            </span>
            {calibration.current_phase && (
              <span className="cal-header__phase mono">
                {PHASE_LABELS[calibration.current_phase] ?? calibration.current_phase}
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          className="cal-header__stop label"
          onClick={onStop}
        >
          CANCEL
        </button>
      </div>

      {/* ── Center: Alignment guides + readiness ── */}
      {(calibration.state === "body_validation" || isScanning) && (
        <div className="cal-center">
          {/* Readiness arc */}
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

          {/* Orientation indicator */}
          {isScanning && calibration.required_orientation && (
            <div className="cal-orientation">
              <span className="cal-orientation__arrow">
                {ORIENTATION_ARROWS[calibration.required_orientation] ?? "●"}
              </span>
              {calibration.orientation && (
                <div className="cal-orientation__progress">
                  <div
                    className="cal-orientation__bar"
                    style={{
                      width: `${calibration.orientation.confirmation_progress * 100}%`,
                      background: calibration.orientation.is_confirmed
                        ? "var(--c-good)"
                        : "var(--c-signal)",
                    }}
                  />
                </div>
              )}
            </div>
          )}
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

        {/* Scan progress dots */}
        <div className="cal-progress">
          {(["front", "right", "left", "back"] as const).map((phase) => {
            const isDone = calibration.completed_phases.includes(phase);
            const isActive = calibration.current_phase === phase;
            return (
              <div
                key={phase}
                className={[
                  "cal-progress__step",
                  isDone ? "cal-progress__step--done" : "",
                  isActive ? "cal-progress__step--active" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <span className="cal-progress__dot">
                  {isDone ? "✓" : isActive ? "●" : "○"}
                </span>
                <span className="cal-progress__label label">
                  {PHASE_LABELS[phase]}
                </span>
              </div>
            );
          })}
          <span className="cal-progress__count mono">
            {completedCount}/4
          </span>
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

      {/* ── Phase captured flash ── */}
      {calibration.phase_just_captured && (
        <div className="cal-captured-flash">
          <span className="cal-captured-flash__icon">✓</span>
          <span className="cal-captured-flash__text label">
            {PHASE_LABELS[calibration.phase_just_captured]?.toUpperCase() ?? ""} CAPTURED
          </span>
        </div>
      )}

      {/* ── Complete state ── */}
      {calibration.state === "complete" && (
        <div className="cal-complete">
          <span className="cal-complete__icon">✓</span>
          <span className="cal-complete__text">Scan Complete</span>
          <span className="cal-complete__sub label">
            All 4 phases captured successfully
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
