/* ============================================================
 * PhysioAI Pro V2 — useSessionSocket
 * ============================================================
 * Owns the WebSocket lifetime for a single live session.
 *
 * RESPONSIBILITIES
 *   • Open the WS to /ws/session
 *   • Parse incoming server messages and split them into pieces
 *     of React state (landmarks, posture score, etc.)
 *   • Expose `sendFrame`, `selectExercise`, `resetReps`,
 *     `startScan`, `sendScanPhaseData` to the UI
 *   • Track a back-pressure flag so we never have more than one
 *     frame in flight per WS — base64 + JSON.stringify is slow
 *     and stacking frames is what kills realtime latency
 * ============================================================ */

import { useCallback, useEffect, useRef, useState } from "react";

import type {
  ClientMessage,
  ExerciseCard,
  Landmark,
  PostureIssue,
  RepState,
  ScanIssue,
  ScanResultMessage,
  CalibrationUpdateMessage,
  ServerMessage,
} from "@/lib/websocket-types";

export type SessionState = {
  connected: boolean;
  landmarks: Landmark[] | null;
  serverFps: number;
  framesSent: number;
  detected: boolean;
  postureScore: number | null;
  postureIssues: PostureIssue[];
  feedbackAr: string;
  recommendations: ExerciseCard[];
  repState: RepState | null;
  exerciseCorrection: string | null;
  scanResult: ScanResultMessage | null;
  calibration: CalibrationUpdateMessage | null;
};

export function useSessionSocket(enabled: boolean, wsUrl?: string) {
  const url = wsUrl ?? (() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/ws/session`;
  })();

  const wsRef = useRef<WebSocket | null>(null);
  const busyRef = useRef(false);

  const [connected, setConnected] = useState(false);
  const [landmarks, setLandmarks] = useState<Landmark[] | null>(null);
  const [serverFps, setServerFps] = useState(0);
  const [framesSent, setFramesSent] = useState(0);
  const [postureScore, setPostureScore] = useState<number | null>(null);
  const [postureIssues, setPostureIssues] = useState<PostureIssue[]>([]);
  const [feedbackAr, setFeedbackAr] = useState("");
  const [recommendations, setRecommendations] = useState<ExerciseCard[]>([]);
  const [repState, setRepState] = useState<RepState | null>(null);
  const [exerciseCorrection, setExerciseCorrection] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<ScanResultMessage | null>(null);
  const [calibration, setCalibration] = useState<CalibrationUpdateMessage | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onclose = () => {
      setConnected(false);
      setLandmarks(null);
      setPostureScore(null);
      setPostureIssues([]);
      setRecommendations([]);
      setRepState(null);
      setExerciseCorrection(null);
      setCalibration(null);
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as ServerMessage;

        if (msg.type === "pose_result") {
          setLandmarks(msg.landmarks);
          setServerFps(msg.fps);
          setPostureScore(msg.posture_score);
          setPostureIssues(msg.posture_issues ?? []);
          setFeedbackAr(msg.feedback_ar ?? "");
          setRecommendations(msg.recommendations ?? []);
          setRepState(msg.rep_state ?? null);
          setExerciseCorrection(msg.exercise_correction ?? null);
        } else if (msg.type === "scan_result") {
          setScanResult(msg);
        } else if (msg.type === "calibration_update") {
          setCalibration(msg as CalibrationUpdateMessage);
        }
        // Silently ignore `connected` / `heartbeat` / `error`.
      } catch {
        // Bad JSON from the server — ignore.
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [enabled, url]);

  /** Send one JPEG frame. Drops the frame if a previous send is still in flight. */
  const sendFrame = useCallback(async (blob: Blob) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || busyRef.current) return;
    busyRef.current = true;
    try {
      const frame = await blobToBase64(blob);
      const msg: ClientMessage = {
        type: "frame",
        timestamp: Date.now() / 1000,
        frame,
      };
      ws.send(JSON.stringify(msg));
      setFramesSent((n) => n + 1);
    } finally {
      busyRef.current = false;
    }
  }, []);

  /** Send any client control message. */
  const sendControl = useCallback((msg: ClientMessage) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(msg));
  }, []);

  const selectExercise = useCallback(
    (exercise_id: string) => sendControl({ type: "select_exercise", exercise_id }),
    [sendControl]
  );
  const resetReps = useCallback(
    () => sendControl({ type: "reset_reps" }),
    [sendControl]
  );
  const startScan = useCallback(
    () => sendControl({ type: "start_scan" }),
    [sendControl]
  );
  const sendScanPhaseData = useCallback(
    (phase: string, landmarks: number[][]) =>
      sendControl({ type: "scan_phase_data", phase, landmarks }),
    [sendControl]
  );

  const startCalibration = useCallback(
    () => sendControl({ type: "start_calibration" }),
    [sendControl]
  );
  const stopCalibration = useCallback(
    () => {
      sendControl({ type: "stop_calibration" });
      setCalibration(null);
    },
    [sendControl]
  );

  const detected = Array.isArray(landmarks) && landmarks.length === 33;

  return {
    connected,
    landmarks,
    serverFps,
    framesSent,
    detected,
    postureScore,
    postureIssues,
    feedbackAr,
    recommendations,
    repState,
    exerciseCorrection,
    scanResult,
    calibration,
    sendFrame,
    selectExercise,
    resetReps,
    startScan,
    sendScanPhaseData,
    startCalibration,
    stopCalibration,
  };
}

/* ── Helpers ── */
function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1] ?? "");
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
