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
import math

from app.services.ai.exercises.base import (
    BaseExerciseTracker,
)
from app.services.ai.geometry import calculate_angle

logger = logging.getLogger(__name__)

LM_RIGHT_SHOULDER = 12
LM_RIGHT_ELBOW = 14
LM_RIGHT_WRIST = 16
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24

# Tunable thresholds (degrees)
EXTEND_THRESHOLD_DEG = 140.0  # Fully extended
RETURN_THRESHOLD_DEG = 85.0   # Bent to start/finish rep

# Config
EMA_ALPHA = 0.35
MIN_VISIBILITY = 0.5
COOLDOWN_FRAMES = 15

def get_distance(p1, p2):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))

class ElbowTracker(BaseExerciseTracker):
    exercise_id = "elbow"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reps = 0
        self.phase_name = "READY"
        self._smoothed_angle = None
        self._cooldown_counter = 0

    def process(self, landmarks: np.ndarray) -> None:
        if landmarks is None or landmarks.shape[0] < 33:
            return

        if self._cooldown_counter > 0:
            self._cooldown_counter -= 1

        # ── Visibility Filtering ──
        required_lms = [LM_RIGHT_SHOULDER, LM_RIGHT_ELBOW, LM_RIGHT_WRIST]
        if landmarks.shape[1] > 3:
            visibilities = [landmarks[i][3] for i in required_lms]
            min_vis = min(visibilities)
            if min_vis < MIN_VISIBILITY:
                return
        
        shoulder = landmarks[LM_RIGHT_SHOULDER]
        elbow = landmarks[LM_RIGHT_ELBOW]
        wrist = landmarks[LM_RIGHT_WRIST]

        # ── Body Normalization Metrics ──
        # Optional: compute arm lengths to log proportionality, 
        # but angles inherently normalize scale!
        upper_arm_length = get_distance(shoulder[:2], elbow[:2])
        lower_arm_length = get_distance(elbow[:2], wrist[:2])
        normalized_arm_extension = get_distance(shoulder[:2], wrist[:2]) / (upper_arm_length + lower_arm_length + 1e-6)

        # ── 3D Angle Calculation ──
        # Using 3D landmarks inherently handles mirrored coordinates and avoids 2D aspect ratio squishing.
        raw_angle = calculate_angle(shoulder[:3], elbow[:3], wrist[:3])

        # ── Lazy Baseline & Smoothing ──
        if getattr(self, "_smoothed_angle", None) is None:
            self._smoothed_angle = raw_angle
            self.phase_name = "READY"
            return

        self._smoothed_angle = (EMA_ALPHA * raw_angle) + ((1 - EMA_ALPHA) * self._smoothed_angle)
        elbow_angle = self._smoothed_angle

        logger.debug("elbow_tracking",
                     current_phase=self.phase_name,
                     elbow_angle=elbow_angle,
                     normalized_arm_extension=normalized_arm_extension,
                     cooldown_active=(self._cooldown_counter > 0))

        # ── State Machine ──
        if self.phase_name == "READY" or self.phase_name == "RESET_READY":
            self.phase_name = "READY"
            if elbow_angle >= EXTEND_THRESHOLD_DEG and self._cooldown_counter == 0:
                self.phase_name = "ARM_EXTENDED"
                self._last_feedback_ar = "ممتاز، اثنِ ذراعك الآن"
                logger.debug("threshold_crossed", phase="ARM_EXTENDED", elbow_angle=elbow_angle)

        elif self.phase_name == "ARM_EXTENDED":
            if elbow_angle <= RETURN_THRESHOLD_DEG:
                self.phase_name = "ARM_RETURNED"
                logger.debug("threshold_crossed", phase="ARM_RETURNED", elbow_angle=elbow_angle)

        elif self.phase_name == "ARM_RETURNED":
            self.phase_name = "REP_COMPLETE"
            self._reps += 1
            self._last_feedback_ar = "أحسنت، كرر الحركة"
            logger.debug("rep_incremented", reps=self._reps, state_reset=True)
            
            # Clean Reset
            self.phase_name = "RESET_READY"
            self._cooldown_counter = COOLDOWN_FRAMES

    def to_rep_state(self) -> dict:
        return {
            "exercise_id": self.exercise_id,
            "reps": self._reps,
            "phase": self.phase_name,
            "last_feedback_ar": getattr(self, "_last_feedback_ar", ""),
            "quality_score": 100,
            "similarity": 1.0,
        }
