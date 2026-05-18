"""
============================================================
PhysioAI Pro V2 - Front-Facing Detector
============================================================
PURPOSE
    Confirms the user is facing the camera directly.
    Uses eye/nose/shoulder symmetry — no profile or back
    detection needed.

TEMPORAL SMOOTHING
    Maintains a rolling buffer of recent detections and only
    confirms front-facing when seen for N consecutive frames.
============================================================
"""

from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)

# MediaPipe landmark indices.
LM_NOSE = 0
LM_LEFT_EYE = 2
LM_RIGHT_EYE = 5
LM_LEFT_EAR = 7
LM_RIGHT_EAR = 8
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12

_VIS_THRESHOLD = 0.40
_CONFIRMATION_FRAMES = 8


@dataclass
class FrontFacingResult:
    """Result of front-facing detection for a single frame."""
    is_front_facing: bool = False
    is_confirmed: bool = False
    confirmation_progress: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "is_front_facing": self.is_front_facing,
            "is_confirmed": self.is_confirmed,
            "confirmation_progress": round(self.confirmation_progress, 2),
            "confidence": round(self.confidence, 2),
        }


class FrontFacingDetector:
    """
    Detects if the user is facing the camera. One instance per client.
    """

    def __init__(self, confirmation_frames: int = _CONFIRMATION_FRAMES) -> None:
        self._confirmation_frames = confirmation_frames
        self._consecutive_count: int = 0

    def detect(self, landmarks: Optional[np.ndarray]) -> FrontFacingResult:
        """Detect if user is front-facing."""
        result = FrontFacingResult()

        if landmarks is None or landmarks.shape[0] < 33:
            self._consecutive_count = 0
            return result

        # Check key landmark visibility.
        nose_vis = float(landmarks[LM_NOSE, 3])
        l_eye_vis = float(landmarks[LM_LEFT_EYE, 3])
        r_eye_vis = float(landmarks[LM_RIGHT_EYE, 3])
        l_sh_vis = float(landmarks[LM_LEFT_SHOULDER, 3])
        r_sh_vis = float(landmarks[LM_RIGHT_SHOULDER, 3])

        # Front-facing requires: nose + both eyes + both shoulders visible.
        both_eyes = l_eye_vis >= _VIS_THRESHOLD and r_eye_vis >= _VIS_THRESHOLD
        nose_ok = nose_vis >= _VIS_THRESHOLD
        both_sh = l_sh_vis >= _VIS_THRESHOLD and r_sh_vis >= _VIS_THRESHOLD

        if not (both_eyes and nose_ok and both_sh):
            self._consecutive_count = 0
            return result

        # Check nose is roughly centered between shoulders.
        nose_x = float(landmarks[LM_NOSE, 0])
        sh_center_x = (float(landmarks[LM_LEFT_SHOULDER, 0]) + float(landmarks[LM_RIGHT_SHOULDER, 0])) / 2.0
        nose_offset = abs(nose_x - sh_center_x)

        # Ear symmetry check.
        l_ear_vis = float(landmarks[LM_LEFT_EAR, 3])
        r_ear_vis = float(landmarks[LM_RIGHT_EAR, 3])
        ear_sym = abs(l_ear_vis - r_ear_vis)

        is_front = nose_offset < 0.09 and ear_sym < 0.35
        result.is_front_facing = is_front
        result.confidence = min(nose_vis, l_eye_vis, r_eye_vis) * (1.0 - nose_offset * 4) if is_front else 0.0

        # Temporal confirmation.
        if is_front:
            self._consecutive_count += 1
        else:
            self._consecutive_count = 0

        progress = min(1.0, self._consecutive_count / self._confirmation_frames)
        result.confirmation_progress = progress
        result.is_confirmed = self._consecutive_count >= self._confirmation_frames

        return result

    def reset(self) -> None:
        """Clear confirmation history."""
        self._consecutive_count = 0
