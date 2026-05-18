"""
============================================================
PhysioAI Pro V2 - Calibration FSM (Front-Only)
============================================================
PURPOSE
    Defines the states and transitions for the simplified
    front-only calibration system. All multi-orientation
    states have been removed.

STATES
    IDLE           — waiting for user to start
    INITIALIZING   — camera warming up, first frames arriving
    BODY_DETECTION — waiting for a body to appear in frame
    BODY_VALIDATION— body visible; validating centering,
                     visibility, and confidence
    FRONT_SCAN     — capturing front-facing posture data
    PROCESSING     — scan captured; running analysis
    COMPLETE       — analysis done; results ready
    ERROR          — unrecoverable issue

TRANSITION RULES
    Every transition is guarded by validation conditions
    evaluated per-frame. The FSM never advances on its own.
============================================================
"""

from enum import Enum
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class CalibrationState(str, Enum):
    """All states in the calibration pipeline."""
    IDLE = "idle"
    INITIALIZING = "initializing"
    BODY_DETECTION = "body_detection"
    BODY_VALIDATION = "body_validation"
    FRONT_SCAN = "front_scan"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


# Human-readable names for each state.
STATE_NAMES = {
    CalibrationState.IDLE: "Ready",
    CalibrationState.INITIALIZING: "Initializing",
    CalibrationState.BODY_DETECTION: "Detecting Body",
    CalibrationState.BODY_VALIDATION: "Validating Position",
    CalibrationState.FRONT_SCAN: "Front Scan",
    CalibrationState.PROCESSING: "Processing",
    CalibrationState.COMPLETE: "Complete",
    CalibrationState.ERROR: "Error",
}

# Valid transitions map.
VALID_TRANSITIONS = {
    CalibrationState.IDLE: {CalibrationState.INITIALIZING, CalibrationState.ERROR},
    CalibrationState.INITIALIZING: {CalibrationState.BODY_DETECTION, CalibrationState.ERROR},
    CalibrationState.BODY_DETECTION: {CalibrationState.BODY_VALIDATION, CalibrationState.ERROR},
    CalibrationState.BODY_VALIDATION: {
        CalibrationState.FRONT_SCAN,
        CalibrationState.BODY_DETECTION,
        CalibrationState.ERROR,
    },
    CalibrationState.FRONT_SCAN: {
        CalibrationState.PROCESSING,
        CalibrationState.BODY_DETECTION,
        CalibrationState.ERROR,
    },
    CalibrationState.PROCESSING: {CalibrationState.COMPLETE, CalibrationState.ERROR},
    CalibrationState.COMPLETE: {CalibrationState.IDLE},
    CalibrationState.ERROR: {CalibrationState.IDLE},
}


class CalibrationFSM:
    """
    Finite state machine for the front-only calibration pipeline.
    """

    def __init__(self) -> None:
        self._state = CalibrationState.IDLE
        self._previous_state: Optional[CalibrationState] = None
        self._error_message: Optional[str] = None

    @property
    def state(self) -> CalibrationState:
        return self._state

    @property
    def previous_state(self) -> Optional[CalibrationState]:
        return self._previous_state

    @property
    def state_name(self) -> str:
        return STATE_NAMES.get(self._state, "Unknown")

    @property
    def error_message(self) -> Optional[str]:
        return self._error_message

    @property
    def is_scanning(self) -> bool:
        return self._state == CalibrationState.FRONT_SCAN

    @property
    def is_active(self) -> bool:
        """True if the FSM is anywhere between INITIALIZING and PROCESSING."""
        return self._state not in {
            CalibrationState.IDLE,
            CalibrationState.COMPLETE,
            CalibrationState.ERROR,
        }

    def transition(self, target: CalibrationState, error_msg: str = "") -> bool:
        """
        Attempt a state transition. Returns True if valid, False if rejected.
        """
        if target not in VALID_TRANSITIONS.get(self._state, set()):
            logger.warning(
                "calibration_invalid_transition",
                current=self._state.value,
                target=target.value,
            )
            return False

        self._previous_state = self._state
        self._state = target

        if target == CalibrationState.ERROR:
            self._error_message = error_msg or "An error occurred"
        else:
            self._error_message = None

        logger.info(
            "calibration_state_changed",
            from_state=self._previous_state.value,
            to_state=self._state.value,
        )
        return True

    def reset(self) -> None:
        """Force-reset to IDLE."""
        self._previous_state = self._state
        self._state = CalibrationState.IDLE
        self._error_message = None

    def to_dict(self) -> dict:
        """Serialize FSM state for the wire."""
        return {
            "state": self._state.value,
            "state_name": self.state_name,
            "is_scanning": self.is_scanning,
            "is_active": self.is_active,
            "error_message": self._error_message,
        }
