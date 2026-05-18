/* ============================================================
 * PhysioAI Pro V2 — ExerciseCard
 * ============================================================
 * One clickable card representing a recommended exercise. Shows
 * the Arabic name, English label, target reps and duration, and
 * a small instructions list (Arabic, RTL).
 *
 * When selected, the card becomes the actively tracked exercise
 * — rep counts and FSM phase will start arriving on the WS.
 * ============================================================ */

import type { ExerciseCard as ExerciseCardData } from "@/lib/websocket-types";
import "./ExerciseCardView.css";

type Props = {
  card: ExerciseCardData;
  selected: boolean;
  onSelect: (id: string) => void;
};

export function ExerciseCardView({ card, selected, onSelect }: Props) {
  return (
    <button
      type="button"
      className={`xcard ${selected ? "xcard--active" : ""}`}
      onClick={() => onSelect(card.id)}
      aria-pressed={selected}
    >
      <div className="xcard__head">
        <div className="xcard__names">
          <span className="xcard__name-ar" dir="rtl" lang="ar">{card.name_ar}</span>
          <span className="label xcard__name-en">{card.name_en}</span>
        </div>
        <div className="xcard__meta mono">
          <span>{card.reps} reps</span>
          <span className="xcard__meta-sep" aria-hidden>·</span>
          <span>{card.duration_s}s</span>
        </div>
      </div>

      <ol className="xcard__steps" dir="rtl" lang="ar">
        {card.instructions_ar.slice(0, 3).map((step, i) => (
          <li key={i} className="xcard__step">
            <span className="mono xcard__step-num">{(i + 1).toString().padStart(2, "0")}</span>
            <span className="xcard__step-text">{step}</span>
          </li>
        ))}
      </ol>

      <div className="xcard__footer">
        <span className="label">
          {selected ? "▮ TRACKING" : "TAP TO TRACK"}
        </span>
      </div>
    </button>
  );
}
