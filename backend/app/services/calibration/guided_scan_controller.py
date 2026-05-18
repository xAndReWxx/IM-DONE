"""
============================================================
PhysioAI Pro V2 - Guided Scan Controller (Front-Only)
============================================================
PURPOSE
    Orchestrates the front-only calibration pipeline. Single
    `process()` call per frame that:
      1. Runs validators on current landmarks
      2. Decides whether to advance the FSM
      3. Captures front scan data when conditions are met
      4. Generates guidance messages and voice prompts
      5. Returns a complete calibration update for the WS

FLOW
    IDLE → INITIALIZING → BODY_DETECTION → BODY_VALIDATION
         → FRONT_SCAN → PROCESSING → COMPLETE

VOICE THROTTLING
    Same guidance message won't repeat within 5 seconds.

FAILURE RECOVERY
    If the user leaves the frame during FRONT_SCAN, the
    controller drops back to BODY_DETECTION. The user can
    resume without losing progress.
============================================================
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from app.services.calibration.scan_fsm import CalibrationState, CalibrationFSM
from app.services.calibration.body_validator import BodyValidator, BodyValidationResult
from app.services.calibration.orientation_detector import FrontFacingDetector, FrontFacingResult
from app.services.calibration.stability_detector import StabilityDetector, StabilityResult
from app.services.calibration.confidence_analyzer import ConfidenceAnalyzer, ConfidenceResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Voice cooldown.
_VOICE_COOLDOWN = 5.0
# Frames of "no body" before dropping to BODY_DETECTION.
_BODY_LOST_THRESHOLD = 15
# Frames to wait in INITIALIZING.
_INIT_FRAMES = 5


@dataclass
class CalibrationUpdate:
    """
    Complete calibration state sent to the frontend each frame.
    """
    state: str = "idle"
    state_name: str = "Ready"
    is_active: bool = False

    body_validation: Optional[dict] = None
    front_facing: Optional[dict] = None
    stability: Optional[dict] = None
    confidence: Optional[dict] = None

    guidance_messages: List[str] = field(default_factory=list)
    voice_message: Optional[str] = None

    scan_captured: bool = False
    readiness_score: float = 0.0
    error_message: Optional[str] = None

    captured_landmarks: Optional[List[List[float]]] = None

    def to_dict(self) -> dict:
        return {
            "type": "calibration_update",
            "state": self.state,
            "state_name": self.state_name,
            "is_active": self.is_active,
            "body_validation": self.body_validation,
            "front_facing": self.front_facing,
            "stability": self.stability,
            "confidence": self.confidence,
            "guidance_messages": self.guidance_messages,
            "voice_message": self.voice_message,
            "scan_captured": self.scan_captured,
            "readiness_score": round(self.readiness_score, 2),
            "error_message": self.error_message,
        }


class GuidedScanController:
    """
    Per-client calibration controller. Create one when scan
    starts, call `process()` every frame, discard when done.
    """

    def __init__(self) -> None:
        self._fsm = CalibrationFSM()
        self._body_validator = BodyValidator()
        self._front_detector = FrontFacingDetector()
        self._stability_detector = StabilityDetector()
        self._confidence_analyzer = ConfidenceAnalyzer()

        # Captured scan data.
        self._scan_data: Optional[List[List[float]]] = None

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
    def scan_data(self) -> Optional[List[List[float]]]:
        return self._scan_data

    def start(self) -> CalibrationUpdate:
        """Start the calibration pipeline."""
        self._fsm.reset()
        self._scan_data = None
        self._init_frame_count = 0
        self._no_body_count = 0
        self._front_detector.reset()
        self._stability_detector.reset()

        self._fsm.transition(CalibrationState.INITIALIZING)

        return CalibrationUpdate(
            state=self._fsm.state.value,
            state_name=self._fsm.state_name,
            is_active=True,
            guidance_messages=["Initializing camera..."],
            voice_message="Starting scan. Please stand in front of the camera.",
        )

    def process(self, landmarks: Optional[np.ndarray]) -> CalibrationUpdate:
        """
        Process one frame through the calibration pipeline.
        """
        update = CalibrationUpdate()
        current_state = self._fsm.state

        # Run all validators.
        body_result = self._body_validator.validate(landmarks)
        front_result = self._front_detector.detect(landmarks)
        stability_result = self._stability_detector.update(landmarks)
        confidence_result = self._confidence_analyzer.analyze(landmarks)

        update.body_validation = body_result.to_dict()
        update.front_facing = front_result.to_dict()
        update.stability = stability_result.to_dict()
        update.confidence = confidence_result.to_dict()

        # ── State-specific logic ──

        if current_state == CalibrationState.INITIALIZING:
            self._handle_initializing(update)

        elif current_state == CalibrationState.BODY_DETECTION:
            self._handle_body_detection(update, body_result)

        elif current_state == CalibrationState.BODY_VALIDATION:
            self._handle_body_validation(
                update, body_result, front_result,
                stability_result, confidence_result,
            )

        elif current_state == CalibrationState.FRONT_SCAN:
            self._handle_front_scan(
                update, landmarks, body_result, front_result,
                stability_result, confidence_result,
            )

        elif current_state == CalibrationState.PROCESSING:
            update.guidance_messages.append("Analyzing your posture...")
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

        return update

    def mark_processing_complete(self) -> CalibrationUpdate:
        """Called when analysis is done."""
        self._fsm.transition(CalibrationState.COMPLETE)
        return CalibrationUpdate(
            state=CalibrationState.COMPLETE.value,
            state_name="Complete",
            is_active=False,
            guidance_messages=["Scan complete! View your results below."],
            voice_message="Scan complete. Your results are ready.",
        )

    def reset(self) -> None:
        """Full reset."""
        self._fsm.reset()
        self._scan_data = None
        self._front_detector.reset()
        self._stability_detector.reset()
        self._init_frame_count = 0
        self._no_body_count = 0

    # ── State handlers ──

    def _handle_initializing(self, update: CalibrationUpdate) -> None:
        self._init_frame_count += 1
        update.guidance_messages.append("Camera warming up...")
        if self._init_frame_count >= _INIT_FRAMES:
            self._fsm.transition(CalibrationState.BODY_DETECTION)
            update.guidance_messages.append("Step into the camera frame")
            update.voice_message = "Please step into the camera frame so I can see your full body."

    def _handle_body_detection(
        self, update: CalibrationUpdate, body_result: BodyValidationResult,
    ) -> None:
        if body_result.body_visible:
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
        front_result: FrontFacingResult,
        stability_result: StabilityResult,
        confidence_result: ConfidenceResult,
    ) -> None:
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

        if not front_result.is_front_facing:
            update.guidance_messages.append("Face the camera directly")
        if not stability_result.is_stable:
            update.guidance_messages.append("Stand still")

        # Readiness score.
        readiness = 0.0
        if body_result.is_valid:
            readiness += 0.3
        if front_result.is_confirmed:
            readiness += 0.2
        if stability_result.stability_confirmed:
            readiness += 0.25
        if confidence_result.is_acceptable:
            readiness += 0.25
        update.readiness_score = readiness

        # All checks pass → advance to FRONT_SCAN.
        if (body_result.is_valid and
                front_result.is_confirmed and
                stability_result.stability_confirmed and
                confidence_result.is_acceptable):
            self._fsm.transition(CalibrationState.FRONT_SCAN)
            self._stability_detector.reset()
            update.voice_message = self._throttled_voice(
                "Great positioning! Hold still for the scan."
            )
        else:
            if not body_result.body_centered:
                update.voice_message = self._throttled_voice("Center your body in the frame.")
            elif not body_result.body_framed:
                msg = body_result.guidance[0] if body_result.guidance else "Adjust your distance."
                update.voice_message = self._throttled_voice(msg)
            elif not front_result.is_front_facing:
                update.voice_message = self._throttled_voice("Please face the camera directly.")
            elif not stability_result.is_stable:
                update.voice_message = self._throttled_voice("Please stand still.")
            elif not confidence_result.is_acceptable:
                update.voice_message = self._throttled_voice("Improve lighting for better detection.")

    def _handle_front_scan(
        self,
        update: CalibrationUpdate,
        landmarks: Optional[np.ndarray],
        body_result: BodyValidationResult,
        front_result: FrontFacingResult,
        stability_result: StabilityResult,
        confidence_result: ConfidenceResult,
    ) -> None:
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
            update.guidance_messages.append("Stay in frame")
            return

        self._no_body_count = 0

        # Readiness score.
        readiness = 0.0
        if front_result.is_confirmed:
            readiness += 0.35
        elif front_result.is_front_facing:
            readiness += 0.15 * front_result.confirmation_progress
        if stability_result.stability_confirmed:
            readiness += 0.35
        elif stability_result.is_stable:
            readiness += 0.15
        if confidence_result.is_acceptable:
            readiness += 0.3
        update.readiness_score = readiness

        # Guidance.
        if not front_result.is_front_facing:
            update.guidance_messages.append("Face the camera directly")
            update.voice_message = self._throttled_voice("Face the camera directly.")
        elif not front_result.is_confirmed:
            pct = int(front_result.confirmation_progress * 100)
            update.guidance_messages.append(f"Hold steady... confirming ({pct}%)")
        else:
            update.guidance_messages.append("Orientation confirmed!")

        if not stability_result.is_stable:
            update.guidance_messages.append("Stand still")
        elif not stability_result.stability_confirmed:
            update.guidance_messages.append("Almost there... keep holding")

        if not confidence_result.is_acceptable:
            update.guidance_messages.extend(confidence_result.guidance)

        # ── CAPTURE condition: all validators pass ──
        if (front_result.is_confirmed and
                stability_result.stability_confirmed and
                confidence_result.is_acceptable and
                landmarks is not None):

            landmark_list = landmarks.tolist()
            self._scan_data = landmark_list
            update.scan_captured = True
            update.captured_landmarks = landmark_list

            logger.info(
                "front_scan_captured",
                confidence=confidence_result.overall_confidence,
                stability=stability_result.stability_score,
            )

            # Advance to PROCESSING.
            self._fsm.transition(CalibrationState.PROCESSING)
            update.voice_message = "Scan captured. Analyzing your posture now."

    # ── Voice throttling ──

    def _throttled_voice(self, text: str) -> Optional[str]:
        now = time.monotonic()
        if text == self._last_voice_text and (now - self._last_voice_time) < _VOICE_COOLDOWN:
            return None
        self._last_voice_time = now
        self._last_voice_text = text
        return text
