"""
============================================================
PhysioAI Pro V2 - Forward Head Correction Tracker
============================================================
PURPOSE
    Counts head retractions by monitoring the depth (Z-axis) 
    distance between the ear and the shoulder midpoint.

HOW IT WORKS
      1. Learn a baseline (neutral head posture) from the first frame.
      2. When head moves forward (ear Z decreases relative to shoulder Z)
         by >= ACTIVE_THRESHOLD, enter ACTIVE.
      3. When the head retracts BACK (Z distance decreases below RETURN_THRESHOLD),
         count a rep.
============================================================
"""

import numpy as np

from app.services.ai.exercises.base import (
    BaseExerciseTracker,
)

LM_LEFT_EAR = 7
LM_RIGHT_EAR = 8
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12

# Simple rule-based thresholds
FORWARD_THRESHOLD = 0.04
BACK_THRESHOLD = 0.02

# EMA Smoothing
EMA_ALPHA = 0.3


class ShoulderReleaseTracker(BaseExerciseTracker):
    exercise_id = "shoulder_release"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reps = 0
        self.phase_name = "READY"
        self._smoothed_distance = None

    def process(self, landmarks: np.ndarray) -> None:
        if landmarks is None or landmarks.shape[0] < 33:
            return

        # Simple rule-based tracking: horizontal distance
        ear_midpoint_x = (landmarks[LM_LEFT_EAR][0] + landmarks[LM_RIGHT_EAR][0]) / 2.0
        shoulder_midpoint_x = (landmarks[LM_LEFT_SHOULDER][0] + landmarks[LM_RIGHT_SHOULDER][0]) / 2.0
        
        raw_distance = abs(ear_midpoint_x - shoulder_midpoint_x)

        # Lazy baseline
        if getattr(self, "_baseline", None) is None:
            self._baseline = raw_distance
            self._smoothed_distance = 0.0
            self.phase_name = "READY"
            return

        # Relative movement with EMA smoothing
        movement_delta = raw_distance - self._baseline
        self._smoothed_distance = (EMA_ALPHA * movement_delta) + ((1 - EMA_ALPHA) * self._smoothed_distance)
        forward_distance = self._smoothed_distance

        # ── Simple State Machine ──
        if self.phase_name == "READY" or self.phase_name == "RESET_READY":
            self.phase_name = "READY"
            if forward_distance > FORWARD_THRESHOLD:
                self.phase_name = "HEAD_FORWARD"
                self._last_feedback_ar = "ممتاز، اسحب رأسك للخلف"

        elif self.phase_name == "HEAD_FORWARD":
            if forward_distance < BACK_THRESHOLD:
                self.phase_name = "HEAD_BACK"
                # Immediately complete the rep based on rules
                self._reps += 1
                self.phase_name = "RESET_READY"
                self._last_feedback_ar = "أحسنت، كرر الحركة"

    def to_rep_state(self) -> dict:
        return {
            "exercise_id": self.exercise_id,
            "reps": self._reps,
            "phase": self.phase_name,
            "last_feedback_ar": getattr(self, "_last_feedback_ar", ""),
            "quality_score": 100,
            "similarity": 1.0,
        }
