import { ExerciseCardView } from "@/components/ExerciseCardView";
import { PostureGauge } from "@/components/PostureGauge";
import type { FinalScanResult } from "./SessionManager";
import "./RecommendationScreen.css";

type Props = {
  finalScanResult: FinalScanResult;
  onBack: () => void;
  onSelectExercise: (id: string) => void;
  onRescan: () => void;
};

export function RecommendationScreen({ finalScanResult, onBack, onSelectExercise, onRescan }: Props) {
  return (
    <div className="recommendation-screen">
      <header className="recommendation-screen__header">
        <div className="recommendation-screen__header-left">
          <button type="button" className="btn-back label" onClick={onBack}>
            ← EXIT
          </button>
          <span className="label brand">PhysioAI · RESULTS</span>
        </div>
        <button type="button" className="btn-rescan label" onClick={onRescan}>
          RESCAN POSTURE
        </button>
      </header>

      <main className="recommendation-screen__main">
        {/* Left Column: AI Summary & Posture Results */}
        <section className="recommendation-screen__summary">
          <h2 className="label section-title">POSTURE ANALYSIS SUMMARY</h2>
          
          <div className="summary-panel">
            <PostureGauge score={finalScanResult.postureScore} />
          </div>

          <div className="posture-summary-list">
            <h3 className="label summary-subtitle">DETECTED CONDITIONS</h3>
            <ul className="summary-list">
              {finalScanResult.postureIssues.map((issue, idx) => (
                <li key={idx} className="summary-list-item">
                  <span className="issue-type">{issue.type.replace(/_/g, " ").toUpperCase()}</span>
                  <span className={`issue-severity severity-${issue.severity}`}>{issue.severity}</span>
                </li>
              ))}
              {finalScanResult.postureIssues.length === 0 && (
                <li className="summary-list-item">
                  <span className="issue-type">NO ISSUES DETECTED</span>
                </li>
              )}
            </ul>
          </div>

        </section>

        {/* Right Column: Exercise Recommendations */}
        <section className="recommendation-screen__exercises">
          <div className="exercises-header">
            <h2 className="label section-title">RECOMMENDED EXERCISES</h2>
            <span className="label exercises-count">
              {finalScanResult.recommendations.length} SUGGESTED
            </span>
          </div>

          <div className="exercises-grid">
            {finalScanResult.recommendations.map((card) => (
              <ExerciseCardView
                key={card.id}
                card={card}
                selected={false}
                onSelect={onSelectExercise}
              />
            ))}
            
            {finalScanResult.recommendations.length === 0 && (
              <div className="exercises-empty">
                <span className="label">No issues detected. Excellent posture!</span>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
