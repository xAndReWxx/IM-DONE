"""
============================================================
PhysioAI Pro V2 - Shoulder Release Tracker
============================================================
PURPOSE
    Counts shoulder release / arm raise reps by monitoring the
    wrist-to-shoulder vertical angle.

HOW IT WORKS
    A shoulder release involves raising the arms laterally,
    which increases the angle between wrist and shoulder.

      1. Learn a baseline (arms at rest) from the first frame.
      2. When wrist rises above shoulder by >= ACTIVE_THRESHOLD,
         enter ACTIVE.
      3. When the raise exceeds HOLD_THRESHOLD, enter HOLD.
      4. After holding >= hold_duration_target, enter RETURNING.
      5. When arms return near baseline, count a rep.

TARGETS
    Raised/uneven shoulders, rounded shoulders.
============================================================
"""

import numpy as np

from app.services.ai.exercises.base import (
    BaseExerciseTracker,
    ExercisePhase,
)
from app.services.ai.geometry import vertical_angle


# MediaPipe landmark indices.
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_WRIST = 15
LM_RIGHT_WRIST = 16

# Tunable thresholds (degrees).
ACTIVE_THRESHOLD_DEG = 15.0    # wrist must rise this much to start
HOLD_THRESHOLD_DEG = 25.0      # full raise depth
RETURN_THRESHOLD_DEG = 8.0     # close enough to baseline = rest


class ShoulderReleaseTracker(BaseExerciseTracker):
    exercise_id = "shoulder_release"

    def process(self, landmarks: np.ndarray) -> None:
        if landmarks is None or landmarks.shape[0] < 33:
            return

        # Average of both sides for symmetry.
        left_angle = vertical_angle(
            landmarks[LM_LEFT_WRIST][:2],
            landmarks[LM_LEFT_SHOULDER][:2],
        )
        right_angle = vertical_angle(
            landmarks[LM_RIGHT_WRIST][:2],
            landmarks[LM_RIGHT_SHOULDER][:2],
        )
        current_angle = (left_angle + right_angle) / 2.0

        # Lazy baseline.
        if self._baseline is None:
            self._baseline = current_angle
            return

        # Raising arms makes the angle increase (wrist goes higher).
        angle_rise = current_angle - self._baseline

        # ── FSM transitions ──
        if self._phase == ExercisePhase.IDLE:
            if angle_rise >= ACTIVE_THRESHOLD_DEG:
                self._transition(ExercisePhase.ACTIVE, feedback_ar="ممتاز، ارفع ذراعيك")

        elif self._phase == ExercisePhase.ACTIVE:
            if angle_rise >= HOLD_THRESHOLD_DEG:
                self._transition(ExercisePhase.HOLD, feedback_ar="ثبّت لمدة ٣ ثوان")
            elif angle_rise < ACTIVE_THRESHOLD_DEG / 2:
                self._transition(ExercisePhase.IDLE)

        elif self._phase == ExercisePhase.HOLD:
            if angle_rise < HOLD_THRESHOLD_DEG - 8.0:
                self._transition(ExercisePhase.RETURNING, feedback_ar="أنزل ببطء")
            elif self._hold_elapsed() >= self._hold_duration_target:
                self._transition(ExercisePhase.RETURNING, feedback_ar="ممتاز، أنزل ببطء")

        elif self._phase == ExercisePhase.RETURNING:
            if angle_rise <= RETURN_THRESHOLD_DEG:
                self._count_rep()
                self._transition(ExercisePhase.IDLE)
