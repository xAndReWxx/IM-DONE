"""
============================================================
PhysioAI Pro V2 - Chin Tuck Tracker
============================================================
PURPOSE
    Counts chin-tuck reps by watching the ear→shoulder angle.

HOW IT WORKS
    A chin tuck pulls the head BACK relative to the shoulders.
    On screen, this makes the line from ear to shoulder more
    vertical (smaller angle). We:

      1. Learn a baseline angle from the user's first frame.
      2. When the angle drops by ≥ 8°, enter ACTIVE.
      3. When it drops by ≥ 12°, enter HOLD and start timing.
      4. After holding ≥ hold_duration_target seconds, enter RETURNING.
      5. When the angle climbs back near baseline, count a rep and idle.

WHY USE A LIVE BASELINE?
    People stand at different distances from the camera and have
    different neck shapes. Learning the baseline lets us count
    reps reliably regardless of body type.
============================================================
"""

import numpy as np

from app.services.ai.exercises.base import (
    BaseExerciseTracker,
    ExercisePhase,
)
from app.services.ai.geometry import vertical_angle
from app.services.ai.posture_analyzer import LM_LEFT_EAR, LM_LEFT_SHOULDER


# Tunable thresholds. Could be promoted to settings later.
ACTIVE_THRESHOLD_DEG = 8.0   # how much the angle must drop to start a rep
HOLD_THRESHOLD_DEG = 12.0    # how deep the tuck needs to go to count
RETURN_THRESHOLD_DEG = 4.0   # close enough to baseline = back at rest


class ChinTuckTracker(BaseExerciseTracker):
    exercise_id = "chin_tuck"

    def process(self, landmarks: np.ndarray) -> None:
        if landmarks is None or landmarks.shape[0] < 33:
            return

        # Use the left side (visible in profile or front views).
        ear = landmarks[LM_LEFT_EAR][:2]
        shoulder = landmarks[LM_LEFT_SHOULDER][:2]
        current_angle = vertical_angle(ear, shoulder)

        # Lazy baseline — captured the first time we see real landmarks.
        if self._baseline is None:
            self._baseline = current_angle
            return

        angle_drop = self._baseline - current_angle  # positive when tucked in

        # ── FSM transitions ──
        if self._phase == ExercisePhase.IDLE:
            if angle_drop >= ACTIVE_THRESHOLD_DEG:
                self._transition(ExercisePhase.ACTIVE)

        elif self._phase == ExercisePhase.ACTIVE:
            if angle_drop >= HOLD_THRESHOLD_DEG:
                self._transition(ExercisePhase.HOLD, feedback_ar="ثبّت لمدة ٣ ثوان")
            elif angle_drop < ACTIVE_THRESHOLD_DEG / 2:
                # User abandoned the tuck before reaching depth — back to idle.
                self._transition(ExercisePhase.IDLE)

        elif self._phase == ExercisePhase.HOLD:
            if angle_drop < HOLD_THRESHOLD_DEG - 4.0:
                # Released too early — still count the attempt as returning.
                self._transition(ExercisePhase.RETURNING, feedback_ar="عد ببطء")
            elif self._hold_elapsed() >= self._hold_duration_target:
                self._transition(ExercisePhase.RETURNING, feedback_ar="ممتاز، عد ببطء")

        elif self._phase == ExercisePhase.RETURNING:
            if angle_drop <= RETURN_THRESHOLD_DEG:
                self._count_rep()
                self._transition(ExercisePhase.IDLE)
