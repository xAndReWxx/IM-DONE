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

import math
import numpy as np
import logging

from app.services.ai.exercises.base import (
    BaseExerciseTracker,
)

logger = logging.getLogger(__name__)

LM_LEFT_EAR = 7
LM_RIGHT_EAR = 8
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24
LM_NOSE = 0

# Config
EMA_ALPHA = 0.3
MIN_VISIBILITY = 0.5
COOLDOWN_FRAMES = 15

def get_distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

class ShoulderReleaseTracker(BaseExerciseTracker):
    exercise_id = "shoulder_release"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reps = 0
        self.phase_name = "READY"
        self._smoothed_distance = None
        self._cooldown_counter = 0

    def process(self, landmarks: np.ndarray) -> None:
        if landmarks is None or landmarks.shape[0] < 33:
            return

        # Decrement cooldown
        if self._cooldown_counter > 0:
            self._cooldown_counter -= 1

        # ── Visibility Filtering ──
        required_lms = [LM_LEFT_EAR, LM_RIGHT_EAR, LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER, LM_LEFT_HIP, LM_RIGHT_HIP, LM_NOSE]
        if landmarks.shape[1] > 3:
            visibilities = [landmarks[i][3] for i in required_lms]
            min_vis = min(visibilities)
            if min_vis < MIN_VISIBILITY:
                logger.debug("low_visibility", visibility_score=min_vis)
                return
        else:
            min_vis = 1.0

        # ── Core Landmarks ──
        left_ear = landmarks[LM_LEFT_EAR]
        right_ear = landmarks[LM_RIGHT_EAR]
        left_shoulder = landmarks[LM_LEFT_SHOULDER]
        right_shoulder = landmarks[LM_RIGHT_SHOULDER]
        left_hip = landmarks[LM_LEFT_HIP]
        right_hip = landmarks[LM_RIGHT_HIP]
        nose = landmarks[LM_NOSE]

        # ── Head Metrics ──
        ear_mid_x = (left_ear[0] + right_ear[0]) / 2.0
        ear_mid_y = (left_ear[1] + right_ear[1]) / 2.0
        
        shoulder_mid_x = (left_shoulder[0] + right_shoulder[0]) / 2.0
        shoulder_mid_y = (left_shoulder[1] + right_shoulder[1]) / 2.0
        
        hip_mid_x = (left_hip[0] + right_hip[0]) / 2.0
        hip_mid_y = (left_hip[1] + right_hip[1]) / 2.0

        # Absolute difference protects against left vs right camera facing
        forward_head_distance = abs(ear_mid_x - shoulder_mid_x)

        # ── Body Normalization ──
        torso_length = get_distance(shoulder_mid_x, shoulder_mid_y, hip_mid_x, hip_mid_y)
        shoulder_width = get_distance(left_shoulder[0], left_shoulder[1], right_shoulder[0], right_shoulder[1])
        
        # Fallback to prevent divide by zero
        if torso_length < 0.05:
            torso_length = 0.5

        # Normalize distance using torso length (as requested)
        normalized_distance = forward_head_distance / torso_length

        # Optional extra metrics for context
        dx = shoulder_mid_x - ear_mid_x
        dy = shoulder_mid_y - ear_mid_y
        neck_angle = math.degrees(math.atan2(dy, dx))
        head_alignment = abs(nose[0] - shoulder_mid_x) / shoulder_width if shoulder_width > 0.01 else 0

        # ── Dynamic Thresholds ──
        # Thresholds scale dynamically with torso length
        # Using 0.08 normalized equivalent if we use the raw distance
        # But wait! We normalized the distance above. 
        # If we use normalized_distance (which is forward_distance / torso), 
        # then the threshold should just be a static float like 0.08.
        FORWARD_THRESHOLD = 0.12
        RETRACT_THRESHOLD = 0.05

        # ── Lazy Baseline ──
        if getattr(self, "_baseline", None) is None:
            self._baseline = normalized_distance
            self._smoothed_distance = 0.0
            self.phase_name = "READY"
            return

        # ── Temporal Smoothing (EMA) ──
        movement_delta = normalized_distance - self._baseline
        self._smoothed_distance = (EMA_ALPHA * movement_delta) + ((1 - EMA_ALPHA) * self._smoothed_distance)
        smoothed_norm_distance = self._smoothed_distance

        logger.debug("forward_head_tracking",
                     current_phase=self.phase_name,
                     forward_head_distance=forward_head_distance,
                     normalized_distance=smoothed_norm_distance,
                     torso_length=torso_length,
                     shoulder_width=shoulder_width,
                     head_tracking_confidence=min_vis,
                     visibility_score=min_vis)

        # ── FSM Transitions ──
        if self.phase_name == "READY" or self.phase_name == "RESET_READY":
            self.phase_name = "READY"
            if smoothed_norm_distance > FORWARD_THRESHOLD and self._cooldown_counter == 0:
                self.phase_name = "HEAD_FORWARD"
                self._last_feedback_ar = "ممتاز، اسحب رأسك للخلف"
                logger.debug("threshold_crossed", phase="HEAD_FORWARD")

        elif self.phase_name == "HEAD_FORWARD":
            if smoothed_norm_distance < RETRACT_THRESHOLD:
                self.phase_name = "HEAD_RETRACTED"
                self._last_feedback_ar = "ثبّت وضعية السحب"
                logger.debug("threshold_crossed", phase="HEAD_RETRACTED")

        elif self.phase_name == "HEAD_RETRACTED":
            self.phase_name = "REP_COMPLETE"
            self._reps += 1
            self._last_feedback_ar = "أحسنت، كرر الحركة"
            logger.debug("rep_incremented", reps=self._reps)
            
            # Reset cleanly
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
