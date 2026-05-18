"""
============================================================
PhysioAI Pro V2 - Thoracic Extension Tracker
============================================================
PURPOSE
    Counts thoracic-extension reps by watching the spine angle
    open up (user arches their upper back backward).

HOW IT WORKS
    Spine angle = the interior angle at the hip vertex between
    the shoulder and the knee (shoulder-hip-knee). As the user
    extends their thoracic spine, this angle GROWS larger than
    their seated baseline.

      1. Lazy-learn the baseline spine angle from frame 1.
      2. When the angle exceeds baseline + 10°, enter ACTIVE.
      3. When it exceeds baseline + 18°, enter HOLD.
      4. After holding, enter RETURNING.
      5. Once back near baseline, count the rep.
============================================================
"""

import numpy as np

from app.services.ai.exercises.base import (
    BaseExerciseTracker,
    ExercisePhase,
)
from app.services.ai.geometry import calculate_angle_2d


LM_L_SHOULDER = 11
LM_L_HIP = 23
LM_L_KNEE = 25

ACTIVE_INCREASE_DEG = 10.0
HOLD_INCREASE_DEG = 18.0
RETURN_INCREASE_DEG = 4.0


class ThoracicExtensionTracker(BaseExerciseTracker):
    exercise_id = "thoracic_extension"

    def process(self, landmarks: np.ndarray) -> None:
        if landmarks is None or landmarks.shape[0] < 33:
            return

        sh = landmarks[LM_L_SHOULDER][:2]
        hip = landmarks[LM_L_HIP][:2]
        knee = landmarks[LM_L_KNEE][:2]

        spine_angle = calculate_angle_2d(sh, hip, knee)

        if self._baseline is None:
            self._baseline = spine_angle
            return

        increase = spine_angle - self._baseline

        if self._phase == ExercisePhase.IDLE:
            if increase >= ACTIVE_INCREASE_DEG:
                self._transition(ExercisePhase.ACTIVE)

        elif self._phase == ExercisePhase.ACTIVE:
            if increase >= HOLD_INCREASE_DEG:
                self._transition(ExercisePhase.HOLD, feedback_ar="افتح صدرك أكثر")
            elif increase < ACTIVE_INCREASE_DEG / 2:
                self._transition(ExercisePhase.IDLE)

        elif self._phase == ExercisePhase.HOLD:
            if increase < HOLD_INCREASE_DEG - 5:
                self._transition(ExercisePhase.RETURNING)
            elif self._hold_elapsed() >= self._hold_duration_target:
                self._transition(ExercisePhase.RETURNING, feedback_ar="عد ببطء للوضع الطبيعي")

        elif self._phase == ExercisePhase.RETURNING:
            if increase <= RETURN_INCREASE_DEG:
                self._count_rep()
                self._transition(ExercisePhase.IDLE)
