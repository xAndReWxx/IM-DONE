"""
============================================================
PhysioAI Pro V2 - Exercise FSM (Finite State Machine)
============================================================
PURPOSE
    Every tracked exercise follows the same four-phase loop:

        idle  →  active  →  hold  →  returning  →  idle  (rep++)

    Concrete exercise trackers (chin tuck, wall angel, thoracic
    extension) plug their own measurement logic into transitions
    of this base FSM. This keeps the rep-counting boilerplate
    in one place so each exercise file stays small and focused.

PHASES (matches the frontend's PHASE_LABELS)
    idle       — user is at rest position
    active     — user is moving INTO the target position
    hold       — target reached, holding for the required duration
    returning  — user is moving back to rest; on full return, rep++

DESIGNED FOR EXTENSION
    To add a new exercise, subclass BaseExerciseTracker and
    implement process(). Use self._transition() to move between
    states. Use self._reps to read the current count.
============================================================
"""

import time
from enum import Enum
from typing import List, Optional

import numpy as np

from app.config import settings
from app.models.packets import RepState


class ExercisePhase(str, Enum):
    """Phases of one exercise rep."""
    IDLE = "idle"
    ACTIVE = "active"
    HOLD = "hold"
    RETURNING = "returning"


# Friendly Arabic phase labels (also redefined client-side for snappier UI).
ARABIC_PHASE_FEEDBACK = {
    ExercisePhase.IDLE:      "استعداد",
    ExercisePhase.ACTIVE:    "ممتاز، استمر",
    ExercisePhase.HOLD:      "ثبّت قليلًا",
    ExercisePhase.RETURNING: "عُد ببطء",
}


class BaseExerciseTracker:
    """
    Per-connection rep tracker base class.

    Subclasses override `process(landmarks)` to compute the
    exercise-specific signal (e.g. ear-shoulder angle) and call
    `self._transition()` to drive the FSM.
    """

    # Subclasses MUST set this — used in the RepState packet.
    exercise_id: str = "base"

    def __init__(self, hold_duration: float | None = None):
        self._phase = ExercisePhase.IDLE
        self._reps = 0
        self._hold_start_time: float = 0.0
        self._hold_duration_target: float = (
            hold_duration if hold_duration is not None else settings.hold_duration_seconds
        )
        self._last_feedback_ar: str = ""
        # Subclasses can use this to lazily learn the user's neutral pose.
        self._baseline: Optional[float] = None

    # ── Public API used by AIEngine ──

    @property
    def reps(self) -> int:
        return self._reps

    @property
    def phase(self) -> ExercisePhase:
        return self._phase

    def reset(self) -> None:
        """Zero the counter and restart the FSM. Keeps the baseline."""
        self._phase = ExercisePhase.IDLE
        self._reps = 0
        self._hold_start_time = 0.0
        self._last_feedback_ar = ""

    def hard_reset(self) -> None:
        """Full reset, including baseline (used when switching exercises)."""
        self.reset()
        self._baseline = None

    def to_rep_state(self) -> RepState:
        """Serialize the current state into the wire packet shape."""
        return RepState(
            exercise_id=self.exercise_id,
            reps=self._reps,
            phase=self._phase.value,
            last_feedback_ar=self._last_feedback_ar,
        )

    def process(self, landmarks: np.ndarray) -> None:
        """Subclasses implement: update FSM based on landmarks."""
        raise NotImplementedError

    # ── Internal FSM helpers (used by subclasses) ──

    def _transition(self, new_phase: ExercisePhase, feedback_ar: str | None = None) -> None:
        """Move to a new phase, marking hold-start time if needed."""
        if new_phase == ExercisePhase.HOLD and self._phase != ExercisePhase.HOLD:
            self._hold_start_time = time.monotonic()
        self._phase = new_phase
        if feedback_ar is not None:
            self._last_feedback_ar = feedback_ar
        else:
            self._last_feedback_ar = ARABIC_PHASE_FEEDBACK.get(new_phase, "")

    def _hold_elapsed(self) -> float:
        """Seconds spent in the current hold."""
        return time.monotonic() - self._hold_start_time

    def _count_rep(self) -> None:
        """Increment the rep counter. Convenience for subclasses."""
        self._reps += 1
        self._last_feedback_ar = f"{self._reps} — ممتاز"
