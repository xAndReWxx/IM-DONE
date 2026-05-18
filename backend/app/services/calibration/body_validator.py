"""
============================================================
PhysioAI Pro V2 - Body Validator (Front-Only)
============================================================
PURPOSE
    Validates that the user's body is properly positioned for
    a front-facing scan. Checks:
      1. Key landmarks visible (nose, shoulders, hips)
      2. Body centered in frame
      3. Body properly framed (not too close/far)

    Front-only — no side-profile or back-view logic.
============================================================
"""

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)

# MediaPipe landmark indices.
LM_NOSE = 0
LM_LEFT_EYE = 2
LM_RIGHT_EYE = 5
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24

# Minimum visibility to consider a landmark "visible".
_MIN_VISIBILITY = 0.45

# Body center must be within this fraction of frame center.
_CENTER_TOLERANCE_X = 0.22
_CENTER_TOLERANCE_Y = 0.28

# Body height should occupy this fraction of the frame.
_MIN_BODY_HEIGHT = 0.40
_MAX_BODY_HEIGHT = 0.95

# Required landmarks for front-facing validation.
_REQUIRED_LANDMARKS = {
    "nose": [LM_NOSE],
    "left_shoulder": [LM_LEFT_SHOULDER],
    "right_shoulder": [LM_RIGHT_SHOULDER],
    "left_hip": [LM_LEFT_HIP],
    "right_hip": [LM_RIGHT_HIP],
}


@dataclass
class BodyValidationResult:
    """Result of body validation for a single frame."""
    is_valid: bool = False
    body_visible: bool = False
    body_centered: bool = False
    body_framed: bool = False
    guidance: List[str] = field(default_factory=list)
    body_center_x: float = 0.5
    body_center_y: float = 0.5
    body_height_ratio: float = 0.0

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "body_visible": self.body_visible,
            "body_centered": self.body_centered,
            "body_framed": self.body_framed,
            "guidance": self.guidance,
            "body_center_x": round(self.body_center_x, 3),
            "body_center_y": round(self.body_center_y, 3),
            "body_height_ratio": round(self.body_height_ratio, 3),
        }


class BodyValidator:
    """Front-facing body validator."""

    def validate(self, landmarks: Optional[np.ndarray]) -> BodyValidationResult:
        """
        Validate body positioning from a (33, 4) landmark array.

        Args:
            landmarks: (33, 4) array of [x, y, z, visibility], or None.

        Returns:
            BodyValidationResult with checks and guidance.
        """
        result = BodyValidationResult()

        if landmarks is None or landmarks.shape[0] < 33:
            result.guidance.append("No body detected. Step into frame.")
            return result

        # ── Check 1: Key landmarks visible ──
        missing = []
        for name, indices in _REQUIRED_LANDMARKS.items():
            for idx in indices:
                if landmarks[idx, 3] < _MIN_VISIBILITY:
                    missing.append(name)
                    break

        result.body_visible = len(missing) == 0

        if not result.body_visible:
            if "nose" in missing:
                result.guidance.append("Face the camera")
            if any("shoulder" in m for m in missing):
                result.guidance.append("Show your upper body")
            if any("hip" in m for m in missing):
                result.guidance.append("Move back to show your full body")
            return result

        # ── Check 2: Body centering ──
        points = []
        for idx in [LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER, LM_LEFT_HIP, LM_RIGHT_HIP]:
            points.append(landmarks[idx, :2])
        coords = np.array(points)
        center_x = float(np.mean(coords[:, 0]))
        center_y = float(np.mean(coords[:, 1]))
        result.body_center_x = center_x
        result.body_center_y = center_y

        dx = abs(center_x - 0.5)
        dy = abs(center_y - 0.5)
        result.body_centered = dx <= _CENTER_TOLERANCE_X and dy <= _CENTER_TOLERANCE_Y

        if not result.body_centered:
            if center_x < 0.5 - _CENTER_TOLERANCE_X:
                result.guidance.append("Move right to center yourself")
            elif center_x > 0.5 + _CENTER_TOLERANCE_X:
                result.guidance.append("Move left to center yourself")
            if center_y < 0.5 - _CENTER_TOLERANCE_Y:
                result.guidance.append("Move down slightly")
            elif center_y > 0.5 + _CENTER_TOLERANCE_Y:
                result.guidance.append("Move up slightly")

        # ── Check 3: Body framing ──
        visible_mask = landmarks[:, 3] >= _MIN_VISIBILITY
        if np.any(visible_mask):
            y_vals = landmarks[visible_mask, 1]
            height_ratio = float(np.max(y_vals) - np.min(y_vals))
        else:
            height_ratio = 0.0
        result.body_height_ratio = height_ratio
        result.body_framed = _MIN_BODY_HEIGHT <= height_ratio <= _MAX_BODY_HEIGHT

        if not result.body_framed:
            if height_ratio < _MIN_BODY_HEIGHT:
                result.guidance.append("Move closer to the camera")
            else:
                result.guidance.append("Move backward from the camera")

        # ── Final verdict ──
        result.is_valid = result.body_visible and result.body_centered and result.body_framed

        if result.is_valid and not result.guidance:
            result.guidance.append("Position looks great!")

        return result
