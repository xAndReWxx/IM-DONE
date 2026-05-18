/* ============================================================
 * PhysioAI Pro V2 — RepCounter
 * ============================================================
 * Big tabular-numeric rep counter + phase pill + quality score.
 *
 * The phase comes from the backend exercise FSM or the
 * AI motion tracker:
 *   idle | active | hold | returning | rest | concentric | peak | eccentric
 *
 * When an AI motion template is active, the quality_score (0–100)
 * and similarity (0–1) fields are populated from DTW comparison.
 * ============================================================ */

import type { RepState, RepPhase } from "@/lib/websocket-types";
import "./RepCounter.css";

const PHASE_LABEL_EN: Record<RepPhase, string> = {
  idle:        "READY",
  active:      "GOING",
  hold:        "HOLD",
  returning:   "RETURN",
  rest:        "READY",
  concentric:  "MOVING",
  peak:        "PEAK",
  eccentric:   "RETURN",
};

const PHASE_LABEL_AR: Record<RepPhase, string> = {
  idle:        "استعداد",
  active:      "ممتاز",
  hold:        "ثبّت",
  returning:   "ارجع",
  rest:        "استعداد",
  concentric:  "حركة",
  peak:        "الذروة",
  eccentric:   "عودة",
};

type Props = {
  rep: RepState;
  onReset: () => void;
};

function qualityColor(score: number): string {
  if (score >= 80) return "var(--c-good)";
  if (score >= 50) return "var(--c-signal)";
  return "var(--c-warn, #e05555)";
}

export function RepCounter({ rep, onReset }: Props) {
  const hasQuality = typeof rep.quality_score === "number" && rep.quality_score > 0;
  const hasSimilarity = typeof rep.similarity === "number" && rep.similarity > 0;

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
        <span className="label">{PHASE_LABEL_EN[rep.phase] ?? rep.phase.toUpperCase()}</span>
        <span className="reps__phase-ar" dir="rtl">{PHASE_LABEL_AR[rep.phase] ?? ""}</span>
      </div>

      {/* ── AI Motion Quality Scores ── */}
      {(hasQuality || hasSimilarity) && (
        <div className="reps__quality">
          {hasQuality && (
            <div className="reps__quality-item">
              <span className="label reps__quality-label">FORM</span>
              <span
                className="mono reps__quality-value"
                style={{ color: qualityColor(rep.quality_score!) }}
              >
                {rep.quality_score}
              </span>
            </div>
          )}
          {hasSimilarity && (
            <div className="reps__quality-item">
              <span className="label reps__quality-label">MATCH</span>
              <span className="mono reps__quality-value">
                {Math.round(rep.similarity! * 100)}%
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
