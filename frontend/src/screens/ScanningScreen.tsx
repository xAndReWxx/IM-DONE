import { useState, useEffect, useRef } from "react";
import { CalibrationOverlay } from "@/components/CalibrationOverlay";
import { useArabicVoice } from "@/hooks/useArabicVoice";
import { useSessionSocket } from "@/hooks/useSessionSocket";
import "./ScanningScreen.css";

type Props = {
  session: ReturnType<typeof useSessionSocket>;
  onBack: () => void;
  camError: string | null;
  errorDetail: any;
  camStatus: string;
  startCam: () => void;
};

export function ScanningScreen({ session, onBack, camError, errorDetail, camStatus, startCam }: Props) {
  const [voiceOn, setVoiceOn] = useState(true);
  const { speak: speakAr } = useArabicVoice(voiceOn);

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

  const isCalibrating = session.calibration != null && session.calibration.is_active;

  return (
    <div className="scanning-screen">
      {/* ── Top bar ── */}
      <header className="scanning-screen__topbar">
        <button type="button" className="scanning-screen__back" onClick={onBack}>
          <span className="scanning-screen__back-arrow" aria-hidden>←</span>
          <span className="label">EXIT</span>
        </button>

        <div className="scanning-screen__brand">
          <span className="label scanning-screen__brand-name">PhysioAI · SCAN</span>
        </div>

        <button
          type="button"
          className={`scanning-screen__voice ${voiceOn ? "scanning-screen__voice--on" : ""}`}
          onClick={() => setVoiceOn(v => !v)}
          aria-pressed={voiceOn}
        >
          <span className="label">VOICE {voiceOn ? "ON" : "OFF"}</span>
        </button>
      </header>

      {/* ── Calibration overlay ── */}
      {session.calibration && (session.calibration.is_active || session.calibration.state === "complete") && (
        <CalibrationOverlay
          calibration={session.calibration}
          onStop={session.stopCalibration}
        />
      )}

      {/* ── Camera Errors ── */}
      {camError && (
        <div className="scanning-screen__cam-error">
          <span className="label">
            {errorDetail?.code === "insecure_origin" ? "SECURE CONNECTION REQUIRED" : "CAMERA ERROR"}
          </span>
          <span className="scanning-screen__cam-error-msg">{camError}</span>
          {errorDetail?.isRecoverable !== false && (
            <button type="button" className="scanning-screen__cam-retry label" onClick={startCam}>
              RETRY
            </button>
          )}
        </div>
      )}

      {camStatus === "requesting" && (
        <div className="scanning-screen__cam-error">
          <div className="scanning-screen__cam-loading" />
          <span className="label">REQUESTING CAMERA ACCESS</span>
          <span className="scanning-screen__cam-error-msg">
            Please allow camera permission when prompted
          </span>
        </div>
      )}
    </div>
  );
}
