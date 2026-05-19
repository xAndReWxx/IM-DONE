/* ============================================================
 * PhysioAI Pro V2 — FeedbackPanel
 * ============================================================
 * Shows the most recent Arabic coaching line in large RTL text,
 * along with a sub-line listing detected posture issues. Both
 * fade smoothly when the text changes so the panel doesn't feel
 * like a flickering ticker.
 *
 * The text is intentionally HUGE — this is the single most
 * important UX element for the user during the session.
 * ============================================================ */

import "./FeedbackPanel.css";
import type { PostureIssue } from "@/lib/websocket-types";

type Props = {
  feedbackAr: string;
  issues: any[];
  detected: boolean;
};

// Human-readable English labels for the posture issue keys.
const ISSUE_LABELS_EN: Record<PostureIssue, string> = {
  forward_head:      "FORWARD HEAD",
  rounded_shoulders: "SHOULDER TILT",
  slouching:         "SLOUCH",
};

export function FeedbackPanel({ feedbackAr, issues, detected }: Props) {
  // The feedback line. While no person is detected, show a placeholder.
  const display = detected
    ? (feedbackAr || "—")
    : "في انتظار الكاميرا...";

  return (
    <div className="feedback">
      <div className="feedback__head">
        <span className="label">COACH · LIVE</span>
        <span className="feedback__sep" />
        <span className="label feedback__lang">AR · RTL</span>
      </div>

      <p
        className="feedback__text"
        dir="rtl"
        lang="ar"
        // key forces React to remount the node on text change → CSS fade-in.
        key={display}
      >
        {display}
      </p>

      <div className="feedback__issues">
        {issues.length === 0 ? (
          <span className="label feedback__issues-empty">NO ISSUES DETECTED</span>
        ) : (
          issues.map((iss, idx) => {
            const key = iss.type || iss;
            const label = iss.type 
              ? iss.type.replace(/_/g, " ").toUpperCase() 
              : (ISSUE_LABELS_EN[iss as PostureIssue] || iss);
            
            return (
              <span key={`${key}-${idx}`} className="feedback__issue label">
                <span className="feedback__issue-dot" aria-hidden />
                {label}
              </span>
            );
          })
        )}
      </div>
    </div>
  );
}
