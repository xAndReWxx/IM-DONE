"""
============================================================
PhysioAI Pro V2 - Wall Angel Tracker
============================================================
PURPOSE
    Counts wall-angel reps by watching the elbow angle.

HOW IT WORKS
    A wall angel starts with arms in a "W" shape (elbows bent
    ~90°) and ends in a "Y" shape (arms extended overhead, elbow
    ~170°). We:

      1. Detect movement up when avg elbow angle exceeds 140°.
      2. Detect full extension (HOLD) when it exceeds 165°.
      3. Hold for the target duration.
      4. Detect return when angle drops back below ~100° (back in "W").
      5. Count a rep.

WHY AVERAGE BOTH ELBOWS?
    Wall angels are bilateral — a single-sided angle would miss
    cases where one arm is occluded or shaking. The average is
    more robust to occasional landmark misses.
============================================================
"""

import numpy as np

from app.services.ai.exercises.base import (
    BaseExerciseTracker,
    ExercisePhase,
)
from app.services.ai.geometry import calculate_angle_2d


# MediaPipe indices used for elbow angle: shoulder-elbow-wrist
LM_L_SHOULDER, LM_L_ELBOW, LM_L_WRIST = 11, 13, 15
LM_R_SHOULDER, LM_R_ELBOW, LM_R_WRIST = 12, 14, 16

UP_THRESHOLD_DEG = 140.0       # arms past this = "going up"
EXTENDED_THRESHOLD_DEG = 165.0 # arms past this = at top
DOWN_THRESHOLD_DEG = 100.0     # arms below this = back at "W"


class WallAngelTracker(BaseExerciseTracker):
    exercise_id = "wall_angel"

    def __init__(self):
        # Wall angels need a shorter hold than chin tucks (2s vs 3s).
        super().__init__(hold_duration=2.0)

    def process(self, landmarks: np.ndarray) -> None:
        if landmarks is None or landmarks.shape[0] < 33:
            return

        ls = landmarks[LM_L_SHOULDER][:2]; le = landmarks[LM_L_ELBOW][:2]; lw = landmarks[LM_L_WRIST][:2]
        rs = landmarks[LM_R_SHOULDER][:2]; re = landmarks[LM_R_ELBOW][:2]; rw = landmarks[LM_R_WRIST][:2]

        # Elbow angles (shoulder-elbow-wrist).
        l_angle = calculate_angle_2d(ls, le, lw)
        r_angle = calculate_angle_2d(rs, re, rw)
        avg_angle = (l_angle + r_angle) / 2.0

        if self._phase == ExercisePhase.IDLE:
            if avg_angle >= UP_THRESHOLD_DEG:
                self._transition(ExercisePhase.ACTIVE)

        elif self._phase == ExercisePhase.ACTIVE:
            if avg_angle >= EXTENDED_THRESHOLD_DEG:
                self._transition(ExercisePhase.HOLD, feedback_ar="ثبّت في الأعلى")
            elif avg_angle < UP_THRESHOLD_DEG - 10:
                self._transition(ExercisePhase.IDLE)

        elif self._phase == ExercisePhase.HOLD:
            if avg_angle < EXTENDED_THRESHOLD_DEG - 10:
                self._transition(ExercisePhase.RETURNING)
            elif self._hold_elapsed() >= self._hold_duration_target:
                self._transition(ExercisePhase.RETURNING, feedback_ar="ممتاز، انزل ببطء")

        elif self._phase == ExercisePhase.RETURNING:
            if avg_angle <= DOWN_THRESHOLD_DEG:
                self._count_rep()
                self._transition(ExercisePhase.IDLE)
