/* ============================================================
 * PhysioAI Pro V2 — RepCounter
 * ============================================================
 * Big tabular-numeric rep counter + phase pill. Only renders
 * when the user has selected an exercise (parent decides).
 *
 * The phase comes from the backend exercise FSM:
 *   idle | active | hold | returning
 *
 * We color the phase pill subtly so the user can see at a glance
 * what stage of the rep they're in.
 * ============================================================ */

import type { RepState, RepPhase } from "@/lib/websocket-types";
import "./RepCounter.css";

const PHASE_LABEL_EN: Record<RepPhase, string> = {
  idle:      "READY",
  active:    "GOING",
  hold:      "HOLD",
  returning: "RETURN",
};

const PHASE_LABEL_AR: Record<RepPhase, string> = {
  idle:      "استعداد",
  active:    "ممتاز",
  hold:      "ثبّت",
  returning: "ارجع",
};

type Props = {
  rep: RepState;
  onReset: () => void;
};

export function RepCounter({ rep, onReset }: Props) {
  return (
    <div className={`reps reps--${rep.phase}`}>
      <div className="reps__head">
        <span className="label">REPS</span>
        <button type="button" className="reps__reset label" onClick={onReset}>
          RESET
        </button>
      </div>

      <div className="reps__value mono">
        {rep.reps.toString().padStart(2, "0")}
      </div>

      <div className="reps__phase">
        <span className="reps__phase-dot" aria-hidden />
        <span className="label">{PHASE_LABEL_EN[rep.phase]}</span>
        <span className="reps__phase-ar" dir="rtl">{PHASE_LABEL_AR[rep.phase]}</span>
      </div>
    </div>
  );
}
