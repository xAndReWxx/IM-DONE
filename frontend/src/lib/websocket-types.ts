/* ============================================================
 * PhysioAI Pro V2 — WebSocket Wire Types
 * ============================================================
 * These types are the canonical TypeScript mirror of the backend
 * Pydantic models in backend/app/models/packets.py.
 *
 * If you change one side, change the other in the same commit
 * or the realtime stream will silently break.
 * ============================================================ */

/* ----- Landmark (one MediaPipe body point) ----- */
export type Landmark = {
  x: number;          // 0..1 normalized (left→right)
  y: number;          // 0..1 normalized (top→bottom — image conv)
  z: number;          // relative depth; negative = closer to camera
  visibility: number; // 0..1 model confidence
};

/* ----- Posture issue keys emitted by the backend analyzer ----- */
export type PostureIssue =
  | "forward_head"
  | "rounded_shoulders"
  | "slouching";

/* ----- One recommended exercise card ----- */
export type ExerciseCard = {
  id: string;
  name_ar: string;
  name_en: string;
  reps: number;
  duration_s: number;
  instructions_ar: string[];
};

/* ----- Exercise rep tracker state ----- */
export type RepPhase = "idle" | "active" | "hold" | "returning";
export type RepState = {
  exercise_id: string;
  reps: number;
  phase: RepPhase;
  last_feedback_ar: string;
};

/* ----- Server → Client ----- */
export type ConnectedMessage = {
  type: "connected";
  client_id: string;
  config: {
    max_fps: number;
    target_fps: number;
    max_frame_size: number;
    heartbeat_interval: number;
    ai_ready: boolean;
  };
  message?: string;
};

export type PoseResultMessage = {
  type: "pose_result";
  fps: number;
  landmarks: Landmark[] | null;
  posture_score: number | null;
  posture_issues: PostureIssue[];
  feedback_ar: string;
  recommendations: ExerciseCard[];
  rep_state: RepState | null;
  latency_ms: number;
  skipped?: boolean;
  /** English exercise correction instruction, if any deviation detected. */
  exercise_correction?: string;
};

export type ScanIssue = {
  type: string;
  description: string;
  severity: "mild" | "moderate" | "severe";
};

export type ScanResultMessage = {
  type: "scan_result";
  issues: ScanIssue[];
  recommendations: ExerciseCard[];
  analysis_summary: string;
};

/* ----- Calibration system types ----- */
export type CalibrationState =
  | "idle"
  | "initializing"
  | "body_detection"
  | "body_validation"
  | "front_scan"
  | "right_scan"
  | "left_scan"
  | "back_scan"
  | "processing"
  | "complete"
  | "error";

export type ConfidenceGrade = "good" | "fair" | "poor";

export type BodyValidation = {
  is_valid: boolean;
  body_visible: boolean;
  body_centered: boolean;
  body_framed: boolean;
  guidance: string[];
  body_center_x: number;
  body_center_y: number;
  body_height_ratio: number;
  missing_groups: string[];
};

export type OrientationData = {
  raw_orientation: string;
  confirmed_orientation: string;
  is_confirmed: boolean;
  confirmation_progress: number;
  confidence: number;
};

export type StabilityData = {
  is_stable: boolean;
  stability_score: number;
  avg_displacement: number;
  consecutive_stable: number;
  stability_confirmed: boolean;
};

export type ConfidenceData = {
  overall_confidence: number;
  avg_visibility: number;
  critical_visibility: number;
  grade: ConfidenceGrade;
  is_acceptable: boolean;
  guidance: string[];
};

export type CalibrationUpdateMessage = {
  type: "calibration_update";
  state: CalibrationState;
  state_name: string;
  is_active: boolean;
  body_validation: BodyValidation | null;
  orientation: OrientationData | null;
  stability: StabilityData | null;
  confidence: ConfidenceData | null;
  guidance_messages: string[];
  voice_message: string | null;
  completed_phases: string[];
  current_phase: string | null;
  total_phases: number;
  required_orientation: string | null;
  readiness_score: number;
  error_message: string | null;
  phase_just_captured: string | null;
};

export type ErrorMessage = {
  type: "error";
  code: string;
  message: string;
  details?: string;
};

export type HeartbeatMessage = {
  type: "heartbeat";
  timestamp: number;
  server_time: number;
};

export type ServerMessage =
  | ConnectedMessage
  | PoseResultMessage
  | ScanResultMessage
  | CalibrationUpdateMessage
  | ErrorMessage
  | HeartbeatMessage;

/* ----- Client → Server ----- */
export type FrameMessage = {
  type: "frame";
  timestamp: number;
  frame: string; // base64-encoded JPEG bytes
};

export type SelectExerciseMessage = {
  type: "select_exercise";
  exercise_id: string;
};

export type ResetRepsMessage = {
  type: "reset_reps";
};

export type ClientHeartbeatMessage = {
  type: "heartbeat";
  timestamp?: number;
};

export type StartScanMessage = {
  type: "start_scan";
};

export type ScanPhaseDataMessage = {
  type: "scan_phase_data";
  phase: string;
  landmarks: number[][];
};

export type StartCalibrationMessage = {
  type: "start_calibration";
};

export type StopCalibrationMessage = {
  type: "stop_calibration";
};

export type ClientMessage =
  | FrameMessage
  | SelectExerciseMessage
  | ResetRepsMessage
  | ClientHeartbeatMessage
  | StartScanMessage
  | ScanPhaseDataMessage
  | StartCalibrationMessage
  | StopCalibrationMessage;
