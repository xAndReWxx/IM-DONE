"""
============================================================
PhysioAI Pro V2 - Elbow Tracker
============================================================
PURPOSE
    Counts elbow extension reps by monitoring the angle between
    shoulder, elbow, and wrist.

HOW IT WORKS
    An elbow extension involves straightening the arm.
      1. Baseline is bent elbow.
      2. As elbow straightens, angle increases.
      3. Above ACTIVE_THRESHOLD, enter ACTIVE.
      4. Above HOLD_THRESHOLD, enter HOLD.
      5. After hold, return down to count rep.
============================================================
"""

import numpy as np
import logging

from app.services.ai.exercises.base import (
    BaseExerciseTracker,
)
from app.services.ai.geometry import calculate_angle

logger = logging.getLogger(__name__)

LM_RIGHT_SHOULDER = 12
LM_RIGHT_ELBOW = 14
LM_RIGHT_WRIST = 16

# Tunable thresholds (degrees)
EXTEND_THRESHOLD_DEG = 120.0  # Start extending
COMPLETE_THRESHOLD_DEG = 150.0  # Full extension required
RETURN_THRESHOLD_DEG = 100.0  # Back to bent to complete rep

# EMA Smoothing
EMA_ALPHA = 0.3


class ElbowTracker(BaseExerciseTracker):
    exercise_id = "elbow"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.phase_name = "READY"
        self._smoothed_angle = None
        self._rep_completed = False

    def reset_state(self):
        """Fully reset internal state for the next rep."""
        self.phase_name = "RESET_READY"
        self._rep_completed = False
        self._last_feedback = ""
        # Cooldowns and locks could be reset here
        
        # Transition back to READY immediately
        self.phase_name = "READY"

    def process(self, landmarks: np.ndarray) -> None:
        if landmarks is None or landmarks.shape[0] < 33:
            return

        # Calculate right elbow angle
        raw_angle = calculate_angle(
            landmarks[LM_RIGHT_SHOULDER][:2],
            landmarks[LM_RIGHT_ELBOW][:2],
            landmarks[LM_RIGHT_WRIST][:2],
        )
        
        # EMA Smoothing
        if self._smoothed_angle is None:
            self._smoothed_angle = raw_angle
        else:
            self._smoothed_angle = (EMA_ALPHA * raw_angle) + ((1 - EMA_ALPHA) * self._smoothed_angle)

        current_angle = self._smoothed_angle

        logger.debug("elbow_tracking",
                     current_phase=self.phase_name,
                     elbow_angle=current_angle)

        # ── FSM transitions ──
        if self.phase_name == "READY" or self.phase_name == "REP_COMPLETE":
            if self.phase_name == "REP_COMPLETE":
                self.reset_state()
                
            if current_angle >= EXTEND_THRESHOLD_DEG:
                self.phase_name = "ARM_EXTEND"
                self._last_feedback = "مد كوعك أكثر"
                logger.debug("threshold_crossed", phase="ARM_EXTEND", elbow_angle=current_angle)

        elif self.phase_name == "ARM_EXTEND":
            # Must reach full extension to allow a return
            if current_angle >= COMPLETE_THRESHOLD_DEG:
                self.phase_name = "ARM_RETURN"
                self._last_feedback = "ثبّت، ثم ارجع ببطء"
                logger.debug("threshold_crossed", phase="ARM_RETURN", elbow_angle=current_angle)

        elif self.phase_name == "ARM_RETURN":
            if current_angle <= RETURN_THRESHOLD_DEG:
                self.phase_name = "REP_COMPLETE"
                self._reps += 1
                self._last_feedback_ar = "أحسنت، كرر الحركة"
                self._rep_completed = True
                logger.debug("rep_incremented", reps=self._reps, state_reset=True)

    def to_rep_state(self) -> dict:
        return {
            "exercise_id": self.exercise_id,
            "reps": self._reps,
            "phase": getattr(self, "phase_name", "READY"),
            "last_feedback_ar": getattr(self, "_last_feedback_ar", ""),
            "quality_score": 100,
            "similarity": 1.0,
        }
