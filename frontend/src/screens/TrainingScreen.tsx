import { RepCounter } from "@/components/RepCounter";
import { ExerciseVideoPlayer } from "@/components/ExerciseVideoPlayer";
import { useArabicVoice } from "@/hooks/useArabicVoice";
import { useVoiceGuidance } from "@/hooks/useVoiceGuidance";
import { useSessionSocket } from "@/hooks/useSessionSocket";
import { useEffect, useRef, useState } from "react";
import "./TrainingScreen.css";

type Props = {
  session: ReturnType<typeof useSessionSocket>;
  exerciseId: string;
  onBack: () => void;
};

export function TrainingScreen({ session, exerciseId, onBack }: Props) {
  const [voiceOn, setVoiceOn] = useState(true);
  const { speak: speakEn } = useVoiceGuidance();

  // ── Throttled exercise corrections ──
  const lastCorrectionRef = useRef<string | null>(null);
  const correctionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const correction = session.exerciseCorrection;
    if (!correction || !voiceOn || correction === lastCorrectionRef.current) return;
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
  }, [session.exerciseCorrection, speakEn, voiceOn]);

  const videoSrc = `/exercise_videos/${exerciseId}/${exerciseId}.mp4`;

  return (
    <div className="training-screen">
      {/* LEFT SIDE: Camera Overlay UI (Camera itself is in SessionManager behind this) */}
      <section className="training-screen__left">
        <header className="training-screen__header">
          <button type="button" className="btn-back label" onClick={onBack}>
            ← EXERCISES
          </button>
          
          <button
            type="button"
            className={`btn-voice ${voiceOn ? "btn-voice--on" : ""}`}
            onClick={() => setVoiceOn(v => !v)}
          >
            <span className="label">VOICE {voiceOn ? "ON" : "OFF"}</span>
          </button>
        </header>

        <div className="training-screen__hud">
          {session.repState && (
            <div className="training-screen__rep-widget">
              <RepCounter rep={session.repState} onReset={session.resetReps} />
            </div>
          )}

          {session.exerciseCorrection && (
            <div className="training-screen__correction">
              <span className="label correction-label">AI CORRECTION</span>
              <p className="correction-text">{session.exerciseCorrection}</p>
            </div>
          )}


        </div>
      </section>

      {/* RIGHT SIDE: Tutorial & Info */}
      <section className="training-screen__right">
        <div className="training-screen__right-content">
          <h2 className="label exercise-title">{exerciseId.replace(/_/g, " ")}</h2>
          
          <div className="exercise-video-wrap">
            <ExerciseVideoPlayer src={videoSrc} title={exerciseId.replace(/_/g, " ")} />
          </div>

          <div className="exercise-instructions">
            <span className="label instructions-label">INSTRUCTIONS</span>
            <ul className="instructions-list">
              <li>Follow the movement shown in the video.</li>
              <li>Keep your movements slow and controlled.</li>
              <li>Listen for AI form corrections.</li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}
