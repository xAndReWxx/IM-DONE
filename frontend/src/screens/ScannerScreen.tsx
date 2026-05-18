/* ============================================================
 * PhysioAI Pro V2 — ScannerScreen
 * ============================================================
 * Dual-mode scanning experience:
 *
 * MODE 1: POSTURE ANALYSIS
 *   Camera opens → AI scans posture → results appear → STOP.
 *   No continuous rescanning. Calibration overlay visible.
 *
 * MODE 2: EXERCISE TRACKING
 *   User selects an exercise → exercise tracker activates →
 *   rep counting + corrections. Camera stays live for tracking.
 *
 * IDLE MODE:
 *   After scan completes, landmarks still render (skeleton
 *   overlay) but no analysis runs. Results + exercises visible.
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

import "./ScannerScreen.css";

type Props = {
  onBack: () => void;
};

export function ScannerScreen({ onBack }: Props) {
  const [voiceOn, setVoiceOn] = useState(true);
  const [selectedExerciseId, setSelectedExerciseId] = useState<string | null>(null);

  // Camera lifecycle.
  const {
    videoRef, active: camActive, error: camError,
    errorDetail, status: camStatus, start: startCam, stop: stopCam,
  } = useCamera();

  // WebSocket connection.
  const session = useSessionSocket(true);

  // Frame sender.
  useFrameSender(videoRef, camActive, session.sendFrame);

  // Voice systems.
  const { speak: speakAr } = useArabicVoice(voiceOn);
  const { speak: speakEn } = useVoiceGuidance();

  // Derived state.
  const { aiMode, calibration, scanResult } = session;
  const isCalibrating = calibration != null && calibration.is_active;
  const scanComplete = calibration?.state === "complete" || scanResult != null;
  const isExerciseMode = aiMode === "exercise_tracking";
  const isIdle = aiMode === "idle";

  // ── Open camera on mount ──
  useEffect(() => {
    startCam();
    return () => { stopCam(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Auto-start calibration when WS connects ──
  const hasAutoStarted = useRef(false);
  useEffect(() => {
    if (session.connected && !hasAutoStarted.current) {
      hasAutoStarted.current = true;
      const t = setTimeout(() => session.startCalibration(), 600);
      return () => clearTimeout(t);
    }
  }, [session.connected, session.startCalibration]);

  // ── Throttled Arabic feedback ──
  const lastFeedbackRef = useRef("");
  const feedbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const fb = session.feedbackAr;
    if (!fb || fb === lastFeedbackRef.current) return;
    // Debounce: wait 2s after last change before speaking.
    if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    feedbackTimerRef.current = setTimeout(() => {
      if (!window.speechSynthesis.speaking) {
        lastFeedbackRef.current = fb;
        speakAr(fb);
      }
    }, 2000);
    return () => {
      if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    };
  }, [session.feedbackAr, speakAr]);

  // ── Throttled exercise corrections ──
  const lastCorrectionRef = useRef<string | null>(null);
  const correctionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const correction = session.exerciseCorrection;
    if (!correction || correction === lastCorrectionRef.current) return;
    if (correctionTimerRef.current) clearTimeout(correctionTimerRef.current);
    correctionTimerRef.current = setTimeout(() => {
      if (!window.speechSynthesis.speaking) {
        lastCorrectionRef.current = correction;
        speakEn(correction);
      }
    }, 1500);
    return () => {
      if (correctionTimerRef.current) clearTimeout(correctionTimerRef.current);
    };
  }, [session.exerciseCorrection, speakEn]);

  // ── Exercise select handler ──
  const handleSelectExercise = (id: string) => {
    if (id === selectedExerciseId) {
      // Deselect — return to idle.
      setSelectedExerciseId(null);
      session.stopExercise();
      return;
    }
    setSelectedExerciseId(id);
    session.selectExercise(id);
  };

  // ── Back to results (exit exercise tracking) ──
  const handleBackToResults = () => {
    setSelectedExerciseId(null);
    session.stopExercise();
  };

  // Video URL for the selected exercise.
  const backendOrigin = `${window.location.protocol}//${window.location.hostname}:8000`;
  const videoSrc = selectedExerciseId
    ? `${backendOrigin}/exercise_videos/${selectedExerciseId}.mp4`
    : null;

  return (
    <main className="scanner">
      {/* ── Top bar ── */}
      <header className="scanner__topbar">
        <button type="button" className="scanner__back" onClick={onBack}>
          <span className="scanner__back-arrow" aria-hidden>←</span>
          <span className="label">EXIT</span>
        </button>

        <div className="scanner__brand">
          <span className="label scanner__brand-name">
            {isExerciseMode ? "PhysioAI · EXERCISE" : "PhysioAI · LIVE"}
          </span>
        </div>

        <button
          type="button"
          className={`scanner__voice ${voiceOn ? "scanner__voice--on" : ""}`}
          onClick={() => setVoiceOn(v => !v)}
          aria-pressed={voiceOn}
        >
          <span className="label">VOICE {voiceOn ? "ON" : "OFF"}</span>
        </button>
      </header>

      {/* ── Main: camera + side panels ── */}
      <section className="scanner__main">
        <div className="scanner__camera-wrap">
          <CameraOverlay
            ref={videoRef}
            landmarks={session.landmarks}
            showHint={camActive && !session.detected && !isCalibrating}
          />

          {/* Calibration overlay — only during posture analysis */}
          {calibration && (calibration.is_active || calibration.state === "complete") && !isExerciseMode && (
            <CalibrationOverlay
              calibration={calibration}
              onStop={session.stopCalibration}
            />
          )}

          {camError && (
            <div className="scanner__cam-error">
              <span className="label">
                {errorDetail?.code === "insecure_origin" ? "SECURE CONNECTION REQUIRED" : "CAMERA ERROR"}
              </span>
              <span className="scanner__cam-error-msg">{camError}</span>
              {errorDetail?.isRecoverable !== false && (
                <button type="button" className="scanner__cam-retry label" onClick={startCam}>
                  RETRY
                </button>
              )}
            </div>
          )}

          {camStatus === "requesting" && (
            <div className="scanner__cam-error">
              <div className="scanner__cam-loading" />
              <span className="label">REQUESTING CAMERA ACCESS</span>
              <span className="scanner__cam-error-msg">
                Please allow camera permission when prompted
              </span>
            </div>
          )}

          {/* Exercise mode indicator */}
          {isExerciseMode && selectedExerciseId && (
            <div className="scanner__exercise-badge">
              <span className="label">{selectedExerciseId.replace(/_/g, " ").toUpperCase()}</span>
            </div>
          )}
        </div>

        <aside className="scanner__side">
          {/* ── POSTURE RESULTS (visible in idle mode after scan) ── */}
          {(isIdle && scanComplete) && (
            <>
              <div className="scanner__panel">
                <PostureGauge score={session.postureScore} />
              </div>

              <FeedbackPanel
                feedbackAr={session.feedbackAr}
                issues={session.postureIssues}
                detected={session.detected}
              />

              <div className="scanner__scan-complete">
                <span className="label scanner__scan-complete-label">SCAN COMPLETE</span>
                <button
                  type="button"
                  className="scanner__scan-reset label"
                  onClick={() => {
                    session.stopCalibration();
                    hasAutoStarted.current = false;
                    setTimeout(() => session.startCalibration(), 300);
                  }}
                >
                  RESCAN
                </button>
              </div>
            </>
          )}

          {/* ── CALIBRATION STATUS (during posture analysis) ── */}
          {isCalibrating && calibration && !isExerciseMode && (
            <div className="scanner__cal-status">
              <div className="scanner__cal-status-header">
                <span className="label scanner__cal-status-state">
                  {calibration.state_name.toUpperCase()}
                </span>
                <span className="mono scanner__cal-status-progress">
                  {Math.round(calibration.readiness_score * 100)}%
                </span>
              </div>
              <div className="scanner__cal-status-bar">
                <div
                  className="scanner__cal-status-fill"
                  style={{ width: `${calibration.readiness_score * 100}%` }}
                />
              </div>
              {calibration.guidance_messages[0] && (
                <p className="scanner__cal-status-guidance">
                  {calibration.guidance_messages[0]}
                </p>
              )}
            </div>
          )}

          {/* ── EXERCISE TRACKING PANEL ── */}
          {isExerciseMode && (
            <div className="scanner__exercise-panel">
              <div className="scanner__exercise-panel-header">
                <span className="label scanner__exercise-panel-title">EXERCISE TRACKING</span>
                <button
                  type="button"
                  className="scanner__exercise-back label"
                  onClick={handleBackToResults}
                >
                  ← RESULTS
                </button>
              </div>

              {session.repState && (
                <RepCounter rep={session.repState} onReset={session.resetReps} />
              )}

              {session.exerciseCorrection && (
                <div className="scanner__exercise-correction">
                  <span className="label scanner__exercise-correction-label">AI CORRECTION</span>
                  <p className="scanner__exercise-correction-text">{session.exerciseCorrection}</p>
                </div>
              )}

              {videoSrc && selectedExerciseId && (
                <VideoPlayer
                  src={videoSrc}
                  title={selectedExerciseId.replace(/_/g, " ")}
                />
              )}
            </div>
          )}
        </aside>
      </section>

      {/* ── Exercise recommendations (visible after scan completes, or during exercise mode) ── */}
      {(scanComplete || isExerciseMode) && (
        <section className="scanner__recs">
          <div className="scanner__recs-head">
            <span className="label">
              {isExerciseMode ? "ALL · EXERCISES" : "RECOMMENDED · EXERCISES"}
            </span>
            <span className="scanner__sep" />
            <span className="label scanner__recs-count">
              {session.recommendations.length === 0
                ? "WAITING FOR SCAN"
                : `${session.recommendations.length} SUGGESTED`}
            </span>
          </div>

          {session.recommendations.length === 0 ? (
            <div className="scanner__recs-empty">
              <span className="label">stand in frame · AI will scan your posture</span>
            </div>
          ) : (
            <div className="scanner__recs-grid">
              {session.recommendations.map((card) => (
                <ExerciseCardView
                  key={card.id}
                  card={card}
                  selected={selectedExerciseId === card.id}
                  onSelect={handleSelectExercise}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </main>
  );
}
