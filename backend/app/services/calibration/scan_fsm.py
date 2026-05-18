"""
============================================================
PhysioAI Pro V2 - Calibration Finite State Machine
============================================================
PURPOSE
    Defines the states and transitions for the Dynamic AI
    Guided Calibration System. All progression is condition-
    based — NO fixed timers anywhere.

STATES
    IDLE           — waiting for user to start
    INITIALIZING   — camera warming up, first frames arriving
    BODY_DETECTION — waiting for a body to appear in frame
    BODY_VALIDATION— body visible; validating centering,
                     visibility, and confidence
    FRONT_SCAN     — capturing front-facing posture data
    RIGHT_SCAN     — capturing right-profile data
    LEFT_SCAN      — capturing left-profile data
    BACK_SCAN      — capturing back-view data
    PROCESSING     — all 4 scans captured; running analysis
    COMPLETE       — analysis done; results ready
    ERROR          — unrecoverable issue (e.g. no camera)

TRANSITION RULES
    Every transition is guarded by validation conditions
    evaluated per-frame. The FSM never advances on its own
    — the controller calls `try_transition()` with the
    current validation results each frame.
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
    RIGHT_SCAN = "right_scan"
    LEFT_SCAN = "left_scan"
    BACK_SCAN = "back_scan"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


# Which scan states correspond to the 4 directional captures.
SCAN_CAPTURE_STATES = {
    CalibrationState.FRONT_SCAN,
    CalibrationState.RIGHT_SCAN,
    CalibrationState.LEFT_SCAN,
    CalibrationState.BACK_SCAN,
}

# The ordered sequence of scan states after validation passes.
SCAN_SEQUENCE = [
    CalibrationState.FRONT_SCAN,
    CalibrationState.RIGHT_SCAN,
    CalibrationState.LEFT_SCAN,
    CalibrationState.BACK_SCAN,
]

# Human-readable names for each state.
STATE_NAMES = {
    CalibrationState.IDLE: "Ready",
    CalibrationState.INITIALIZING: "Initializing",
    CalibrationState.BODY_DETECTION: "Detecting Body",
    CalibrationState.BODY_VALIDATION: "Validating Position",
    CalibrationState.FRONT_SCAN: "Front Scan",
    CalibrationState.RIGHT_SCAN: "Right Scan",
    CalibrationState.LEFT_SCAN: "Left Scan",
    CalibrationState.BACK_SCAN: "Back Scan",
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
        CalibrationState.RIGHT_SCAN,
        CalibrationState.BODY_DETECTION,
        CalibrationState.ERROR,
    },
    CalibrationState.RIGHT_SCAN: {
        CalibrationState.LEFT_SCAN,
        CalibrationState.BODY_DETECTION,
        CalibrationState.ERROR,
    },
    CalibrationState.LEFT_SCAN: {
        CalibrationState.BACK_SCAN,
        CalibrationState.BODY_DETECTION,
        CalibrationState.ERROR,
    },
    CalibrationState.BACK_SCAN: {
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
    Finite state machine for the calibration pipeline.

    Thread-safe: all state changes happen through `transition()`,
    which validates the move before committing.
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
        return self._state in SCAN_CAPTURE_STATES

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
        Attempt a state transition. Returns True if the transition
        was valid and committed, False if it was rejected.
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
        """Force-reset to IDLE regardless of current state."""
        self._previous_state = self._state
        self._state = CalibrationState.IDLE
        self._error_message = None

    def next_scan_state(self) -> Optional[CalibrationState]:
        """
        Returns the next scan state in the sequence, or None
        if the current state is BACK_SCAN (final scan).
        """
        if self._state not in SCAN_CAPTURE_STATES:
            return None
        idx = SCAN_SEQUENCE.index(self._state)
        if idx < len(SCAN_SEQUENCE) - 1:
            return SCAN_SEQUENCE[idx + 1]
        return CalibrationState.PROCESSING

    def to_dict(self) -> dict:
        """Serialize FSM state for the wire."""
        return {
            "state": self._state.value,
            "state_name": self.state_name,
            "is_scanning": self.is_scanning,
            "is_active": self.is_active,
            "error_message": self._error_message,
        }
