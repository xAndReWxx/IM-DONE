"""
============================================================
PhysioAI Pro V2 - Guided Scan Controller
============================================================
PURPOSE
    The brain of the Dynamic AI Guided Calibration System.
    Orchestrates the FSM, validators, and detectors into a
    single per-frame `process()` call that:
      1. Runs all validators on the current landmarks
      2. Decides whether to advance the FSM
      3. Captures scan data when conditions are met
      4. Generates guidance messages and voice prompts
      5. Returns a complete calibration state update for the WS

    This is the ONLY class the WebSocket handler needs to
    interact with — everything else is internal.

VOICE THROTTLING
    Voice guidance is throttled to prevent spam. Each guidance
    message has a minimum interval before it can be spoken again.

FAILURE RECOVERY
    If the user leaves the frame during a scan, the controller
    pauses and drops back to BODY_DETECTION, preserving any
    already-captured phases. The user can resume without losing
    progress.
============================================================
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from app.services.calibration.scan_fsm import (
    CalibrationState,
    CalibrationFSM,
    SCAN_SEQUENCE,
)
from app.services.calibration.body_validator import BodyValidator, BodyValidationResult
from app.services.calibration.orientation_detector import (
    Orientation,
    OrientationDetector,
    OrientationResult,
)
from app.services.calibration.stability_detector import StabilityDetector, StabilityResult
from app.services.calibration.confidence_analyzer import ConfidenceAnalyzer, ConfidenceResult
from app.utils.logger import get_logger

logger = get_logger(__name__)


# Map from scan state to required orientation.
_SCAN_TO_ORIENTATION = {
    CalibrationState.FRONT_SCAN: Orientation.FRONT_FACING,
    CalibrationState.RIGHT_SCAN: Orientation.RIGHT_PROFILE,
    CalibrationState.LEFT_SCAN: Orientation.LEFT_PROFILE,
    CalibrationState.BACK_SCAN: Orientation.BACK_VIEW,
}

# Map from scan state to the phase name used in the scan buffer.
_SCAN_TO_PHASE = {
    CalibrationState.FRONT_SCAN: "front",
    CalibrationState.RIGHT_SCAN: "right",
    CalibrationState.LEFT_SCAN: "left",
    CalibrationState.BACK_SCAN: "back",
}

# Voice guidance for each scan state.
_SCAN_VOICE_GUIDANCE = {
    CalibrationState.FRONT_SCAN: "Face the camera directly",
    CalibrationState.RIGHT_SCAN: "Turn your right side to the camera slowly",
    CalibrationState.LEFT_SCAN: "Turn your left side to the camera slowly",
    CalibrationState.BACK_SCAN: "Turn your back to the camera",
}

# Minimum seconds between repeating the same voice guidance.
_VOICE_COOLDOWN = 5.0

# How many frames of "no body" before dropping back to BODY_DETECTION.
_BODY_LOST_THRESHOLD = 15

# Frames to wait in INITIALIZING before moving to BODY_DETECTION.
_INIT_FRAMES = 5


@dataclass
class CalibrationUpdate:
    """
    Complete calibration state update sent to the frontend
    every frame while calibration is active.
    """
    # FSM state.
    state: str = "idle"
    state_name: str = "Ready"
    is_active: bool = False

    # Validation results.
    body_validation: Optional[dict] = None
    orientation: Optional[dict] = None
    stability: Optional[dict] = None
    confidence: Optional[dict] = None

    # Current guidance.
    guidance_messages: List[str] = field(default_factory=list)
    voice_message: Optional[str] = None

    # Scan progress.
    completed_phases: List[str] = field(default_factory=list)
    current_phase: Optional[str] = None
    total_phases: int = 4

    # Required orientation for current state.
    required_orientation: Optional[str] = None

    # Readiness score (0–1): how close we are to capturing.
    readiness_score: float = 0.0

    # Error info.
    error_message: Optional[str] = None

    # When a phase was just captured, this is set.
    phase_just_captured: Optional[str] = None

    # Captured landmark data (only set when phase_just_captured).
    captured_landmarks: Optional[List[List[float]]] = None

    def to_dict(self) -> dict:
        return {
            "type": "calibration_update",
            "state": self.state,
            "state_name": self.state_name,
            "is_active": self.is_active,
            "body_validation": self.body_validation,
            "orientation": self.orientation,
            "stability": self.stability,
            "confidence": self.confidence,
            "guidance_messages": self.guidance_messages,
            "voice_message": self.voice_message,
            "completed_phases": self.completed_phases,
            "current_phase": self.current_phase,
            "total_phases": self.total_phases,
            "required_orientation": self.required_orientation,
            "readiness_score": round(self.readiness_score, 2),
            "error_message": self.error_message,
            "phase_just_captured": self.phase_just_captured,
        }


class GuidedScanController:
    """
    Per-client calibration controller. Create one when scan
    starts, call `process()` every frame, discard when done.
    """

    def __init__(self) -> None:
        self._fsm = CalibrationFSM()
        self._body_validator = BodyValidator()
        self._orientation_detector = OrientationDetector()
        self._stability_detector = StabilityDetector()
        self._confidence_analyzer = ConfidenceAnalyzer()

        # Scan data buffer — preserved across state resets.
        self._scan_buffer: Dict[str, List[List[float]]] = {}
        self._completed_phases: List[str] = []

        # Voice throttling.
        self._last_voice_time: float = 0.0
        self._last_voice_text: str = ""

        # Counters.
        self._init_frame_count: int = 0
        self._no_body_count: int = 0

    @property
    def state(self) -> CalibrationState:
        return self._fsm.state

    @property
    def is_active(self) -> bool:
        return self._fsm.is_active

    @property
    def scan_buffer(self) -> Dict[str, List[List[float]]]:
        return self._scan_buffer

    @property
    def completed_phases(self) -> List[str]:
        return list(self._completed_phases)

    def start(self) -> CalibrationUpdate:
        """Start the calibration pipeline."""
        self._fsm.reset()
        self._scan_buffer.clear()
        self._completed_phases.clear()
        self._init_frame_count = 0
        self._no_body_count = 0
        self._orientation_detector.reset()
        self._stability_detector.reset()

        self._fsm.transition(CalibrationState.INITIALIZING)

        update = CalibrationUpdate(
            state=self._fsm.state.value,
            state_name=self._fsm.state_name,
            is_active=True,
            guidance_messages=["Initializing camera..."],
            voice_message="Starting calibration. Please stand in front of the camera.",
        )
        return update

    def process(self, landmarks: Optional[np.ndarray]) -> CalibrationUpdate:
        """
        Process one frame through the calibration pipeline.

        Args:
            landmarks: (33, 4) array from pose detection, or None.

        Returns:
            CalibrationUpdate with complete state for the frontend.
        """
        update = CalibrationUpdate()
        update.completed_phases = list(self._completed_phases)
        update.total_phases = 4

        current_state = self._fsm.state

        # Run all validators regardless of state.
        body_result = self._body_validator.validate(landmarks)
        orientation_result = self._orientation_detector.detect(landmarks)
        stability_result = self._stability_detector.update(landmarks)
        confidence_result = self._confidence_analyzer.analyze(landmarks)

        update.body_validation = body_result.to_dict()
        update.orientation = orientation_result.to_dict()
        update.stability = stability_result.to_dict()
        update.confidence = confidence_result.to_dict()

        # ── State-specific logic ──

        if current_state == CalibrationState.INITIALIZING:
            self._handle_initializing(update, landmarks)

        elif current_state == CalibrationState.BODY_DETECTION:
            self._handle_body_detection(update, body_result, landmarks)

        elif current_state == CalibrationState.BODY_VALIDATION:
            self._handle_body_validation(
                update, body_result, stability_result, confidence_result
            )

        elif current_state in _SCAN_TO_ORIENTATION:
            self._handle_scan_state(
                update, landmarks, body_result,
                orientation_result, stability_result, confidence_result,
            )

        elif current_state == CalibrationState.PROCESSING:
            update.guidance_messages.append("Analyzing your posture data...")
            update.voice_message = self._throttled_voice("Analyzing your posture. Please wait.")

        elif current_state == CalibrationState.COMPLETE:
            update.guidance_messages.append("Scan complete!")

        elif current_state == CalibrationState.ERROR:
            update.error_message = self._fsm.error_message
            update.guidance_messages.append(self._fsm.error_message or "An error occurred")

        # Fill common fields.
        update.state = self._fsm.state.value
        update.state_name = self._fsm.state_name
        update.is_active = self._fsm.is_active

        if self._fsm.state in _SCAN_TO_ORIENTATION:
            update.required_orientation = _SCAN_TO_ORIENTATION[self._fsm.state].value
            update.current_phase = _SCAN_TO_PHASE.get(self._fsm.state)

        return update

    def mark_processing_complete(self) -> CalibrationUpdate:
        """Called by the handler when 360° analysis is done."""
        self._fsm.transition(CalibrationState.COMPLETE)
        return CalibrationUpdate(
            state=CalibrationState.COMPLETE.value,
            state_name="Complete",
            is_active=False,
            completed_phases=list(self._completed_phases),
            guidance_messages=["Scan complete! View your results below."],
            voice_message="Scan complete. Your results are ready.",
        )

    def reset(self) -> None:
        """Full reset — clears everything."""
        self._fsm.reset()
        self._scan_buffer.clear()
        self._completed_phases.clear()
        self._orientation_detector.reset()
        self._stability_detector.reset()
        self._init_frame_count = 0
        self._no_body_count = 0

    # ── State handlers ──

    def _handle_initializing(
        self,
        update: CalibrationUpdate,
        landmarks: Optional[np.ndarray],
    ) -> None:
        """Wait a few frames for camera to warm up."""
        self._init_frame_count += 1
        update.guidance_messages.append("Camera warming up...")

        if self._init_frame_count >= _INIT_FRAMES:
            self._fsm.transition(CalibrationState.BODY_DETECTION)
            update.guidance_messages.append("Step into the camera frame")
            update.voice_message = "Please step into the camera frame so I can see your full body."

    def _handle_body_detection(
        self,
        update: CalibrationUpdate,
        body_result: BodyValidationResult,
        landmarks: Optional[np.ndarray],
    ) -> None:
        """Waiting for a body to appear."""
        if landmarks is not None and body_result.body_visible:
            self._fsm.transition(CalibrationState.BODY_VALIDATION)
            self._no_body_count = 0
            update.guidance_messages.append("Body detected! Adjusting position...")
            update.voice_message = self._throttled_voice("Body detected. Adjusting your position.")
        else:
            update.guidance_messages.append("Step into the camera frame")
            update.guidance_messages.extend(body_result.guidance)
            update.voice_message = self._throttled_voice(
                "Please stand in front of the camera so I can see your full body."
            )

    def _handle_body_validation(
        self,
        update: CalibrationUpdate,
        body_result: BodyValidationResult,
        stability_result: StabilityResult,
        confidence_result: ConfidenceResult,
    ) -> None:
        """Body visible — validate positioning before scanning."""

        if not body_result.body_visible:
            self._no_body_count += 1
            if self._no_body_count >= _BODY_LOST_THRESHOLD:
                self._fsm.transition(CalibrationState.BODY_DETECTION)
                self._no_body_count = 0
                update.voice_message = self._throttled_voice("I lost sight of you. Please step back into frame.")
            return

        self._no_body_count = 0
        update.guidance_messages.extend(body_result.guidance)
        update.guidance_messages.extend(confidence_result.guidance)

        if not stability_result.is_stable:
            update.guidance_messages.append("Stand still")

        # Compute readiness score.
        readiness = 0.0
        if body_result.is_valid:
            readiness += 0.4
        if stability_result.stability_confirmed:
            readiness += 0.3
        if confidence_result.is_acceptable:
            readiness += 0.3
        update.readiness_score = readiness

        # All checks pass → advance to FRONT_SCAN.
        if (body_result.is_valid and
                stability_result.stability_confirmed and
                confidence_result.is_acceptable):
            self._fsm.transition(CalibrationState.FRONT_SCAN)
            self._stability_detector.reset()  # Reset for new scan state.
            update.voice_message = self._throttled_voice(
                "Great positioning! Now face the camera directly and stand still for the front scan."
            )
        else:
            # Provide guidance voice.
            if not body_result.body_centered:
                update.voice_message = self._throttled_voice("Center your body in the frame.")
            elif not body_result.body_framed:
                update.voice_message = self._throttled_voice(body_result.guidance[0] if body_result.guidance else "Adjust your distance.")
            elif not stability_result.is_stable:
                update.voice_message = self._throttled_voice("Please stand still.")
            elif not confidence_result.is_acceptable:
                update.voice_message = self._throttled_voice("Improve lighting for better detection.")

    def _handle_scan_state(
        self,
        update: CalibrationUpdate,
        landmarks: Optional[np.ndarray],
        body_result: BodyValidationResult,
        orientation_result: OrientationResult,
        stability_result: StabilityResult,
        confidence_result: ConfidenceResult,
    ) -> None:
        """Handle any of the 4 scan capture states."""
        current_state = self._fsm.state
        required_orientation = _SCAN_TO_ORIENTATION[current_state]
        phase_name = _SCAN_TO_PHASE[current_state]

        update.required_orientation = required_orientation.value
        update.current_phase = phase_name

        # Check if body was lost.
        if not body_result.body_visible:
            self._no_body_count += 1
            if self._no_body_count >= _BODY_LOST_THRESHOLD:
                self._fsm.transition(CalibrationState.BODY_DETECTION)
                self._no_body_count = 0
                self._stability_detector.reset()
                update.voice_message = self._throttled_voice(
                    "I lost sight of you. Please step back into frame."
                )
            update.guidance_messages.append("Body not visible. Stay in frame.")
            return

        self._no_body_count = 0

        # Check orientation.
        has_correct_orientation = (
            orientation_result.confirmed_orientation == required_orientation
            and orientation_result.is_confirmed
        )

        # Readiness score for this scan state.
        readiness = 0.0
        if has_correct_orientation:
            readiness += 0.4
        elif orientation_result.raw_orientation == required_orientation:
            readiness += 0.2 * orientation_result.confirmation_progress
        if stability_result.stability_confirmed:
            readiness += 0.3
        elif stability_result.is_stable:
            readiness += 0.15
        if confidence_result.is_acceptable:
            readiness += 0.3
        update.readiness_score = readiness

        # Guidance.
        if not has_correct_orientation:
            scan_guidance = _SCAN_VOICE_GUIDANCE.get(current_state, "Adjust your position")
            update.guidance_messages.append(scan_guidance)

            if orientation_result.raw_orientation == required_orientation:
                progress_pct = int(orientation_result.confirmation_progress * 100)
                update.guidance_messages.append(f"Hold steady... confirming ({progress_pct}%)")
            else:
                update.voice_message = self._throttled_voice(scan_guidance)
        else:
            update.guidance_messages.append("Orientation confirmed!")

        if not stability_result.is_stable:
            update.guidance_messages.append("Stand still")
        else:
            if not stability_result.stability_confirmed:
                update.guidance_messages.append("Almost there... keep holding")

        if not confidence_result.is_acceptable:
            update.guidance_messages.extend(confidence_result.guidance)

        # ── CAPTURE condition: all 3 validators pass ──
        if (has_correct_orientation and
                stability_result.stability_confirmed and
                confidence_result.is_acceptable and
                landmarks is not None):

            # Capture the scan data!
            landmark_list = landmarks.tolist()
            self._scan_buffer[phase_name] = landmark_list
            self._completed_phases.append(phase_name)

            update.phase_just_captured = phase_name
            update.captured_landmarks = landmark_list
            update.completed_phases = list(self._completed_phases)

            logger.info(
                "scan_phase_captured",
                phase=phase_name,
                confidence=confidence_result.overall_confidence,
                stability=stability_result.stability_score,
            )

            # Advance to next scan state.
            next_state = self._fsm.next_scan_state()
            if next_state is not None:
                self._fsm.transition(next_state)
                self._stability_detector.reset()
                self._orientation_detector.reset()

                if next_state == CalibrationState.PROCESSING:
                    update.voice_message = "Excellent! All scans captured. Analyzing your posture now."
                else:
                    next_guidance = _SCAN_VOICE_GUIDANCE.get(next_state, "")
                    update.voice_message = f"Perfect! {phase_name.title()} scan captured. {next_guidance}"

    # ── Voice throttling ──

    def _throttled_voice(self, text: str) -> Optional[str]:
        """
        Return the text if it hasn't been spoken recently,
        otherwise return None.
        """
        now = time.monotonic()
        if text == self._last_voice_text and (now - self._last_voice_time) < _VOICE_COOLDOWN:
            return None
        self._last_voice_time = now
        self._last_voice_text = text
        return text
