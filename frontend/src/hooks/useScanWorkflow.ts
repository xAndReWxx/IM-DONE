/* ============================================================
 * PhysioAI Pro V2 — useScanWorkflow
 * ============================================================
 * Manages the full 360° body scan workflow.
 *
 * Phase sequence:
 *   idle → neutral (5s) → front (4s) → right (4s) → left (4s) → back (4s)
 *   → analyzing → complete
 *
 * Each transition announces itself via speak() (English guidance).
 * ============================================================ */

import { useCallback, useEffect, useRef, useState } from "react";
import { useVoiceGuidance } from "./useVoiceGuidance";

export type ScanPhase =
  | "idle"
  | "neutral"
  | "front"
  | "right"
  | "left"
  | "back"
  | "analyzing"
  | "complete";

export type ScanData = {
  [phase: string]: { landmarks: number[][]; capturedAt: number };
};

type Props = {
  onScanComplete?: (scanData: ScanData) => void;
};

const PHASE_DURATIONS: Partial<Record<ScanPhase, number>> = {
  neutral: 5,
  front:   4,
  right:   4,
  left:    4,
  back:    4,
};

const PHASE_INSTRUCTIONS: Partial<Record<ScanPhase, string>> = {
  neutral: "Stand naturally in a neutral pose, facing the camera.",
  front:   "Face the camera directly. Hold still.",
  right:   "Turn your right side to the camera. Hold still.",
  left:    "Turn your left side to the camera. Hold still.",
  back:    "Turn your back to the camera. Hold still.",
  analyzing: "Analyzing your posture. Please wait.",
};

const PHASE_NAMES: Partial<Record<ScanPhase, string>> = {
  neutral:   "NEUTRAL POSE",
  front:     "FRONT SCAN",
  right:     "RIGHT SCAN",
  left:      "LEFT SCAN",
  back:      "BACK SCAN",
  analyzing: "ANALYZING",
};

const SCAN_PHASES: ScanPhase[] = ["neutral", "front", "right", "left", "back"];
const DATA_PHASES: ScanPhase[] = ["front", "right", "left", "back"];

export function useScanWorkflow({ onScanComplete }: Props = {}) {
  const [phase, setPhase] = useState<ScanPhase>("idle");
  const [countdown, setCountdown] = useState(0);
  const { speak } = useVoiceGuidance();

  const phaseRef = useRef<ScanPhase>("idle");
  const countdownRef = useRef(0);
  const scanDataRef = useRef<ScanData>({});
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const advanceToPhase = useCallback(
    (nextPhase: ScanPhase) => {
      clearTimer();
      phaseRef.current = nextPhase;
      setPhase(nextPhase);

      const duration = PHASE_DURATIONS[nextPhase];
      if (duration !== undefined) {
        countdownRef.current = duration;
        setCountdown(duration);

        const instruction = PHASE_INSTRUCTIONS[nextPhase];
        if (instruction) speak(instruction);

        timerRef.current = setInterval(() => {
          countdownRef.current -= 1;
          setCountdown(countdownRef.current);

          if (countdownRef.current <= 0) {
            clearTimer();
            const idx = SCAN_PHASES.indexOf(phaseRef.current);
            const next = idx >= 0 && idx < SCAN_PHASES.length - 1
              ? SCAN_PHASES[idx + 1]
              : "analyzing";
            advanceToPhase(next);
          }
        }, 1000);
      } else if (nextPhase === "analyzing") {
        speak(PHASE_INSTRUCTIONS.analyzing ?? "Analyzing.");
        setCountdown(0);
        // Brief delay to let "analyzing" render before completing.
        setTimeout(() => {
          phaseRef.current = "complete";
          setPhase("complete");
          onScanComplete?.(scanDataRef.current);
        }, 1800);
      } else if (nextPhase === "complete") {
        setCountdown(0);
      }
    },
    [speak, onScanComplete]
  );

  const startScan = useCallback(() => {
    scanDataRef.current = {};
    advanceToPhase("neutral");
  }, [advanceToPhase]);

  const resetScan = useCallback(() => {
    clearTimer();
    scanDataRef.current = {};
    phaseRef.current = "idle";
    setPhase("idle");
    setCountdown(0);
  }, []);

  // Cleanup on unmount.
  useEffect(() => {
    return () => clearTimer();
  }, []);

  const isScanning =
    phase !== "idle" && phase !== "complete";

  const instructions = PHASE_INSTRUCTIONS[phase] ?? "";
  const phaseName = PHASE_NAMES[phase] ?? "";

  // Progress dots: one per DATA_PHASES (4 phases after neutral).
  const completedDataPhases = DATA_PHASES.filter((p) => {
    const pIdx = SCAN_PHASES.indexOf(p);
    const curIdx = SCAN_PHASES.indexOf(phaseRef.current);
    return curIdx > pIdx;
  });
  const progressDots = DATA_PHASES.map((p) => ({
    phase: p,
    done: completedDataPhases.includes(p),
    active: phaseRef.current === p,
  }));

  return {
    phase,
    countdown,
    instructions,
    phaseName,
    progressDots,
    isScanning,
    startScan,
    resetScan,
  };
}
