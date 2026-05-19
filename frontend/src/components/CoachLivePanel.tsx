import type { SessionState } from "@/hooks/useSessionSocket";
import "./CoachLivePanel.css";

type Props = {
  mode: "scan" | "train";
  session: SessionState | any; // Either live session or final result
};

export function CoachLivePanel({ mode, session }: Props) {
  return (
    <div className="coach-live-panel">
      <div className="coach-live-header">
        <span className="live-indicator"></span>
        <span className="label">REALTIME INSIGHTS</span>
      </div>

      <div className="coach-live-body">
        {mode === "scan" ? (
          <>
            <div className="insight-row">
              <span className="insight-label">SCAN STATUS</span>
              <span className="insight-value">{session.calibration?.is_active ? "SCANNING..." : "IDLE"}</span>
            </div>
            <div className="insight-row">
              <span className="insight-label">POSTURE SCORE</span>
              <span className="insight-value">{session.postureScore ?? "--"} / 100</span>
            </div>
            <div className="insight-row">
              <span className="insight-label">BODY SYMMETRY</span>
              <span className="insight-value">
                {session.postureScore ? (session.postureScore > 80 ? "HIGH" : "LOW") : "--"}
              </span>
            </div>
          </>
        ) : (
          <>
            <div className="insight-row">
              <span className="insight-label">TRACKING MODE</span>
              <span className="insight-value">ACTIVE</span>
            </div>
            <div className="insight-row">
              <span className="insight-label">CURRENT REP</span>
              <span className="insight-value">{session.repState?.reps ?? 0}</span>
            </div>
            <div className="insight-row">
              <span className="insight-label">FORM QUALITY</span>
              <span className="insight-value">
                {session.repState?.quality_score ? `${(session.repState.quality_score * 100).toFixed(0)}%` : "--"}
              </span>
            </div>
            <div className="insight-row">
              <span className="insight-label">LATEST CORRECTION</span>
              <span className="insight-value correction-value">
                {session.exerciseCorrection || "Good form."}
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
