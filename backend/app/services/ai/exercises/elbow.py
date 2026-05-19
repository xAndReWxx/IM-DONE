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

from app.services.ai.exercises.base import (
    BaseExerciseTracker,
    ExercisePhase,
)
from app.services.ai.geometry import calculate_angle


# MediaPipe landmark indices.
LM_LEFT_SHOULDER = 11
LM_LEFT_ELBOW = 13
LM_LEFT_WRIST = 15

LM_RIGHT_SHOULDER = 12
LM_RIGHT_ELBOW = 14
LM_RIGHT_WRIST = 16

# Tunable thresholds (degrees)
ACTIVE_THRESHOLD_DEG = 120.0  # Start extending
HOLD_THRESHOLD_DEG = 150.0    # Full extension
RETURN_THRESHOLD_DEG = 100.0  # Back to bent


class ElbowTracker(BaseExerciseTracker):
    exercise_id = "elbow"

    def process(self, landmarks: np.ndarray) -> None:
        if landmarks is None or landmarks.shape[0] < 33:
            return

        # For simplicity, calculate right elbow extension
        right_angle = calculate_angle(
            landmarks[LM_RIGHT_SHOULDER][:2],
            landmarks[LM_RIGHT_ELBOW][:2],
            landmarks[LM_RIGHT_WRIST][:2],
        )
        
        current_angle = right_angle

        # ── FSM transitions ──
        if self._phase == ExercisePhase.IDLE:
            if current_angle >= ACTIVE_THRESHOLD_DEG:
                self._transition(ExercisePhase.ACTIVE, feedback_ar="مد كوعك")

        elif self._phase == ExercisePhase.ACTIVE:
            if current_angle >= HOLD_THRESHOLD_DEG:
                self._transition(ExercisePhase.HOLD, feedback_ar="ثبّت لمدة ٣ ثوان")
            elif current_angle < ACTIVE_THRESHOLD_DEG - 10.0:
                self._transition(ExercisePhase.IDLE)

        elif self._phase == ExercisePhase.HOLD:
            if current_angle < HOLD_THRESHOLD_DEG - 10.0:
                self._transition(ExercisePhase.RETURNING, feedback_ar="ارجع ببطء")
            elif self._hold_elapsed() >= self._hold_duration_target:
                self._transition(ExercisePhase.RETURNING, feedback_ar="ممتاز، ارجع ببطء")

        elif self._phase == ExercisePhase.RETURNING:
            if current_angle <= RETURN_THRESHOLD_DEG:
                self._count_rep()
                self._transition(ExercisePhase.IDLE)
