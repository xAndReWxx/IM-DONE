import { ExerciseCardView } from "@/components/ExerciseCardView";
import { PostureGauge } from "@/components/PostureGauge";
import { FeedbackPanel } from "@/components/FeedbackPanel";
import { useSessionSocket } from "@/hooks/useSessionSocket";
import "./RecommendationScreen.css";

type Props = {
  session: ReturnType<typeof useSessionSocket>;
  onBack: () => void;
  onSelectExercise: (id: string) => void;
  onRescan: () => void;
};

export function RecommendationScreen({ session, onBack, onSelectExercise, onRescan }: Props) {
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
            <PostureGauge score={session.postureScore} />
          </div>

          <FeedbackPanel
            feedbackAr={session.feedbackAr}
            issues={session.postureIssues}
            detected={session.detected}
          />
        </section>

        {/* Right Column: Exercise Recommendations */}
        <section className="recommendation-screen__exercises">
          <div className="exercises-header">
            <h2 className="label section-title">RECOMMENDED EXERCISES</h2>
            <span className="label exercises-count">
              {session.recommendations.length} SUGGESTED
            </span>
          </div>

          <div className="exercises-grid">
            {session.recommendations.map((card) => (
              <ExerciseCardView
                key={card.id}
                card={card}
                selected={false}
                onSelect={onSelectExercise}
              />
            ))}
            
            {session.recommendations.length === 0 && (
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
