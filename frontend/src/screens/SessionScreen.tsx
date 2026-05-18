/* ============================================================
 * PhysioAI Pro V2 — SessionScreen
 * ============================================================
 * The "AI is watching me" screen. Layout:
 *
 *   [ TOP BAR ]              back · brand · voice toggle
 *   ┌─────────────┬────────┐
 *   │             │ GAUGE  │
 *   │   CAMERA    │--------│
 *   │  + CAL      │ FEEDBK │
 *   │  OVERLAY    │--------│
 *   │             │ SCAN   │
 *   │             │--------│
 *   │             │ VIDEO  │
 *   └─────────────┴────────┘
 *   [ EXERCISE RECOMMENDATIONS ]
 *
 * CALIBRATION SYSTEM (replaces old timer-based scan):
 *   The old useScanWorkflow with fixed countdown timers has
 *   been replaced by the AI-guided calibration system. When
 *   the user presses "START AI SCAN", the backend drives the
 *   entire flow through condition-based state transitions:
 *     - Body detection & validation
 *     - Orientation detection with temporal smoothing
 *     - Stability confirmation
 *     - Confidence gating
 *     - Automatic scan capture & progression
 *
 *   NO fixed timers. NO manual clicks between phases.
 *   Progression is fully automatic when conditions are met.
 * ============================================================ */

import { useEffect, useRef, useState } from "react";

import { CameraOverlay } from "@/components/CameraOverlay";
import { CalibrationOverlay } from "@/components/CalibrationOverlay";
import { ExerciseCardView } from "@/components/ExerciseCardView";
import { FeedbackPanel } from "@/components/FeedbackPanel";
import { PostureGauge } from "@/components/PostureGauge";
import { RepCounter } from "@/components/RepCounter";
import { VideoPlayer } from "@/components/VideoPlayer";

import { useArabicVoice } from "@/hooks/useArabicVoice";
import { useCamera } from "@/hooks/useCamera";
import { useFrameSender } from "@/hooks/useFrameSender";
import { useSessionSocket } from "@/hooks/useSessionSocket";
import { useVoiceGuidance } from "@/hooks/useVoiceGuidance";

import "./SessionScreen.css";

type Props = {
  onBack: () => void;
};

export function SessionScreen({ onBack }: Props) {
  // Voice on by default; user can toggle in the topbar.
  const [voiceOn, setVoiceOn] = useState(true);
  // Selected exercise (controls UI highlight + sends select_exercise to server).
  const [selectedExerciseId, setSelectedExerciseId] = useState<string | null>(null);

  // Camera lifecycle.
  const { videoRef, active: camActive, error: camError, start: startCam, stop: stopCam } = useCamera();
  // WebSocket session.
  const session = useSessionSocket(true);
  // Frame sender ticks once the camera is live.
  useFrameSender(videoRef, camActive, session.sendFrame);
  // Arabic TTS for coaching feedback.
  const { speak: speakAr } = useArabicVoice(voiceOn);
  // English TTS for exercise corrections.
  const { speak: speakEn } = useVoiceGuidance();

  // Calibration state from backend.
  const calibration = session.calibration;
  const isCalibrating = calibration != null && calibration.is_active;
  const calibrationDone = calibration?.state === "complete";

  // ── Open the camera once on mount; close on unmount ──
  useEffect(() => {
    startCam();
    return () => { stopCam(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Speak Arabic feedback when it changes ──
  useEffect(() => {
    speakAr(session.feedbackAr);
  }, [session.feedbackAr, speakAr]);

  // ── Speak exercise corrections (English) when they arrive ──
  const lastCorrectionRef = useRef<string | null>(null);
  useEffect(() => {
    const correction = session.exerciseCorrection;
    if (correction && correction !== lastCorrectionRef.current) {
      lastCorrectionRef.current = correction;
      speakEn(correction);
    }
  }, [session.exerciseCorrection, speakEn]);

  // ── Select handler: update local state + notify server ──
  const handleSelect = (id: string) => {
    if (id === selectedExerciseId) {
      setSelectedExerciseId(null);
      session.resetReps();
      return;
    }
    setSelectedExerciseId(id);
    session.selectExercise(id);
  };

  // Derive video URL for the selected exercise.
  const videoSrc = selectedExerciseId
    ? `http://localhost:8000/exercise_videos/${selectedExerciseId}.mp4`
    : null;

  return (
    <main className="session">
      {/* ── Top bar ── */}
      <header className="session__topbar">
        <button type="button" className="session__back" onClick={onBack}>
          <span className="session__back-arrow" aria-hidden>←</span>
          <span className="label">EXIT</span>
        </button>

        <div className="session__brand">
          <span className="label session__brand-name">PhysioAI · LIVE</span>
        </div>

        <button
          type="button"
          className={`session__voice ${voiceOn ? "session__voice--on" : ""}`}
          onClick={() => setVoiceOn(v => !v)}
          aria-pressed={voiceOn}
        >
          <span className="label">VOICE {voiceOn ? "ON" : "OFF"}</span>
        </button>
      </header>

      {/* ── Main: camera + side panels ── */}
      <section className="session__main">
        <div className="session__camera-wrap">
          <CameraOverlay
            ref={videoRef}
            landmarks={session.landmarks}
            showHint={camActive && !session.detected && !isCalibrating}
          />

          {/* AI Calibration Overlay — replaces old timer-based scan */}
          {calibration && (calibration.is_active || calibration.state === "complete") && (
            <CalibrationOverlay
              calibration={calibration}
              onStop={session.stopCalibration}
            />
          )}

          {camError && (
            <div className="session__cam-error">
              <span className="label">CAMERA ERROR</span>
              <span className="session__cam-error-msg">{camError}</span>
              <button type="button" className="session__cam-retry label" onClick={startCam}>
                RETRY
              </button>
            </div>
          )}
        </div>

        <aside className="session__side">
          <div className="session__panel">
            <PostureGauge score={session.postureScore} />
          </div>

          <FeedbackPanel
            feedbackAr={session.feedbackAr}
            issues={session.postureIssues}
            detected={session.detected}
          />

          {session.repState && selectedExerciseId && (
            <RepCounter rep={session.repState} onReset={session.resetReps} />
          )}

          {/* ── AI-Guided Scan Button (replaces old timer scan) ── */}
          {!isCalibrating && !calibrationDone && (
            <div className="session__scan-idle">
              <button
                type="button"
                className="session__scan-start label"
                onClick={session.startCalibration}
                disabled={!session.connected}
              >
                START AI SCAN
              </button>
            </div>
          )}

          {/* Calibration status summary (side panel) */}
          {isCalibrating && calibration && (
            <div className="session__cal-status">
              <div className="session__cal-status-header">
                <span className="label session__cal-status-state">
                  {calibration.state_name.toUpperCase()}
                </span>
                <span className="mono session__cal-status-progress">
                  {calibration.completed_phases.length}/4
                </span>
              </div>
              <div className="session__cal-status-bar">
                <div
                  className="session__cal-status-fill"
                  style={{ width: `${(calibration.completed_phases.length / 4) * 100}%` }}
                />
              </div>
              {calibration.guidance_messages[0] && (
                <p className="session__cal-status-guidance">
                  {calibration.guidance_messages[0]}
                </p>
              )}
            </div>
          )}

          {/* Scan complete — show rescan option */}
          {calibrationDone && (
            <div className="session__scan-complete">
              <span className="label session__scan-complete-label">SCAN COMPLETE</span>
              <button
                type="button"
                className="session__scan-reset label"
                onClick={() => {
                  session.stopCalibration();
                  // Small delay then restart.
                  setTimeout(() => session.startCalibration(), 300);
                }}
              >
                RESCAN
              </button>
            </div>
          )}

          {/* ── Exercise video player ── */}
          {videoSrc && selectedExerciseId && (
            <VideoPlayer
              src={videoSrc}
              title={selectedExerciseId.replace(/_/g, " ")}
            />
          )}
        </aside>
      </section>

      {/* ── Exercise recommendations ── */}
      <section className="session__recs">
        <div className="session__recs-head">
          <span className="label">RECOMMENDED · EXERCISES</span>
          <span className="session__sep" />
          <span className="label session__recs-count">
            {session.recommendations.length === 0
              ? "WAITING FOR ANALYSIS"
              : `${session.recommendations.length} SUGGESTED`}
          </span>
        </div>

        {session.recommendations.length === 0 ? (
          <div className="session__recs-empty">
            <span className="label">stand in frame · wait for posture analysis</span>
          </div>
        ) : (
          <div className="session__recs-grid">
            {session.recommendations.map((card) => (
              <ExerciseCardView
                key={card.id}
                card={card}
                selected={selectedExerciseId === card.id}
                onSelect={handleSelect}
              />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
