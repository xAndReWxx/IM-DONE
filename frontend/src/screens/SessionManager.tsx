import { useEffect, useRef, useState } from "react";
import { CameraOverlay } from "@/components/CameraOverlay";
import { useCamera } from "@/hooks/useCamera";
import { useFrameSender } from "@/hooks/useFrameSender";
import { useSessionSocket } from "@/hooks/useSessionSocket";
import { ScanningScreen } from "./ScanningScreen";
import { RecommendationScreen } from "./RecommendationScreen";
import { TrainingScreen } from "./TrainingScreen";
import "./SessionManager.css";

type Props = {
  onBack: () => void;
};

export type ScreenState = "scanning" | "recommendation" | "training";

export function SessionManager({ onBack }: Props) {
  const [screen, setScreen] = useState<ScreenState>("scanning");
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

  // ── Open camera on mount ──
  useEffect(() => {
    startCam();
    return () => { stopCam(); };
  }, []);

  // ── Screen Transitions ──
  const { aiMode, calibration, scanResult } = session;
  const isCalibrating = calibration != null && calibration.is_active;
  const scanComplete = calibration?.state === "complete" || scanResult != null;

  // Auto transition from scanning to recommendation when scan completes
  useEffect(() => {
    if (screen === "scanning" && scanComplete) {
      // Small delay to allow the "Scan Complete" animation/state to be seen briefly
      const t = setTimeout(() => {
        setScreen("recommendation");
      }, 1500);
      return () => clearTimeout(t);
    }
  }, [screen, scanComplete]);

  // If we are in recommendation and user selects an exercise, go to training
  const handleSelectExercise = (id: string) => {
    setSelectedExerciseId(id);
    session.selectExercise(id);
    setScreen("training");
  };

  const handleBackToRecommendations = () => {
    setSelectedExerciseId(null);
    session.stopExercise();
    setScreen("recommendation");
  };

  const handleRescan = () => {
    setScreen("scanning");
    session.stopCalibration();
    setTimeout(() => session.startCalibration(), 300);
  };

  // ── Derived View State ──
  // The camera wrapper changes style in training mode (split screen)
  const isTraining = screen === "training";

  return (
    <div className="session-manager">
      {/* ── BACKGROUND CAMERA LAYER ── */}
      <div className={`session-camera-layer ${isTraining ? "session-camera-layer--split" : ""}`}>
        <CameraOverlay
          ref={videoRef}
          landmarks={session.landmarks}
          showHint={camActive && !session.detected && !isCalibrating && screen === "scanning"}
        />
      </div>

      {/* ── OVERLAY SCREENS ── */}
      {screen === "scanning" && (
        <ScanningScreen
          session={session}
          onBack={onBack}
          camError={camError}
          errorDetail={errorDetail}
          camStatus={camStatus}
          startCam={startCam}
        />
      )}

      {screen === "recommendation" && (
        <RecommendationScreen
          session={session}
          onBack={onBack}
          onSelectExercise={handleSelectExercise}
          onRescan={handleRescan}
        />
      )}

      {screen === "training" && selectedExerciseId && (
        <TrainingScreen
          session={session}
          exerciseId={selectedExerciseId}
          onBack={handleBackToRecommendations}
        />
      )}
    </div>
  );
}
