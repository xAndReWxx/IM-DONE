"""
============================================================
PhysioAI Pro V2 - Body Validator (Occlusion-Aware)
============================================================
PURPOSE
    Validates that the user's body is properly positioned for
    a scan capture. Checks:
      1. Full body visibility (key landmarks present)
      2. Body centering (body center near frame center)
      3. Body framing (not too close, not too far)

    OCCLUSION-AWARE VALIDATION:
    The validator adapts its requirements based on the current
    expected orientation. During side-profile scans, it does
    NOT require symmetric landmark visibility:
      • RIGHT_SCAN: only requires right-side landmarks
      • LEFT_SCAN:  only requires left-side landmarks
      • BACK_SCAN:  does not require nose/eyes
      • FRONT_SCAN: requires full symmetric visibility

    This prevents false "body invalid" during legitimate
    side-profile turns where MediaPipe naturally hides
    occluded landmarks.

LANDMARK INDICES (MediaPipe Pose)
    0: nose         7: left_ear      8: right_ear
    11: left_shoulder  12: right_shoulder
    23: left_hip       24: right_hip
    25: left_knee      26: right_knee
    27: left_ankle     28: right_ankle
============================================================
"""

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)


# MediaPipe landmark indices used for body validation.
LM_NOSE = 0
LM_LEFT_EYE = 2
LM_RIGHT_EYE = 5
LM_LEFT_EAR = 7
LM_RIGHT_EAR = 8
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24
LM_LEFT_KNEE = 25
LM_RIGHT_KNEE = 26
LM_LEFT_ANKLE = 27
LM_RIGHT_ANKLE = 28

# Minimum visibility score to consider a landmark "visible".
_MIN_VISIBILITY = 0.45
# Lower threshold for "partially visible" — still usable.
_MIN_PARTIAL_VISIBILITY = 0.25

# Body center must be within this fraction of the frame center.
_CENTER_TOLERANCE_X = 0.22
_CENTER_TOLERANCE_Y = 0.28

# Body bounding box should occupy this fraction of the frame.
_MIN_BODY_HEIGHT_RATIO = 0.40   # relaxed from 0.45 for side views
_MAX_BODY_HEIGHT_RATIO = 0.95

# ── Orientation-specific landmark requirements ──
# Each orientation has "essential" (all must be visible) and
# "desired" (at least one per group) landmark sets.

# FRONT: full symmetric visibility required.
_FRONT_ESSENTIAL = {
    "nose": [LM_NOSE],
    "shoulders": [LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER],
    "hips": [LM_LEFT_HIP, LM_RIGHT_HIP],
}
_FRONT_DESIRED = {
    "knees": [LM_LEFT_KNEE, LM_RIGHT_KNEE],
}

# RIGHT PROFILE: only right-side landmarks required.
# Left side naturally becomes occluded.
_RIGHT_ESSENTIAL = {
    "right_shoulder": [LM_RIGHT_SHOULDER],
    "torso": [LM_RIGHT_HIP],  # at least one hip
}
_RIGHT_DESIRED = {
    "head": [LM_NOSE, LM_RIGHT_EAR],     # at least one
    "hips": [LM_LEFT_HIP, LM_RIGHT_HIP],  # at least one
}

# LEFT PROFILE: mirror of right.
_LEFT_ESSENTIAL = {
    "left_shoulder": [LM_LEFT_SHOULDER],
    "torso": [LM_LEFT_HIP],
}
_LEFT_DESIRED = {
    "head": [LM_NOSE, LM_LEFT_EAR],
    "hips": [LM_LEFT_HIP, LM_RIGHT_HIP],
}

# BACK VIEW: no nose/eyes expected. Shoulders + hips required.
_BACK_ESSENTIAL = {
    "shoulders": [LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER],
}
_BACK_DESIRED = {
    "hips": [LM_LEFT_HIP, LM_RIGHT_HIP],
}

# Default (no orientation context): same as front.
_DEFAULT_ESSENTIAL = _FRONT_ESSENTIAL
_DEFAULT_DESIRED = _FRONT_DESIRED


@dataclass
class BodyValidationResult:
    """Result of body validation for a single frame."""
    is_valid: bool = False

    # Individual checks.
    body_visible: bool = False
    body_centered: bool = False
    body_framed: bool = False

    # Guidance messages to show the user.
    guidance: List[str] = field(default_factory=list)

    # Numeric details for the frontend overlay.
    body_center_x: float = 0.5
    body_center_y: float = 0.5
    body_height_ratio: float = 0.0

    # Missing landmark groups for diagnostics.
    missing_groups: List[str] = field(default_factory=list)

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
            "missing_groups": self.missing_groups,
        }


class BodyValidator:
    """
    Occlusion-aware body validator. Call `validate()` with the
    current orientation context so it knows which landmarks to
    expect.
    """

    def validate(
        self,
        landmarks: Optional[np.ndarray],
        expected_orientation: Optional[str] = None,
    ) -> BodyValidationResult:
        """
        Validate body positioning from a (33, 4) landmark array.

        Args:
            landmarks: (33, 4) array of [x, y, z, visibility].
                       None if no body was detected at all.
            expected_orientation: The orientation the calibration
                system expects. One of:
                  "front_facing", "right_profile", "left_profile",
                  "back_view", or None (default = front rules).
                This controls which landmarks are required.

        Returns:
            BodyValidationResult with checks and guidance.
        """
        result = BodyValidationResult()

        # No landmarks at all — body not detected.
        if landmarks is None or landmarks.shape[0] < 33:
            result.guidance.append("No body detected. Step into frame.")
            return result

        # Select orientation-specific landmark requirements.
        essential, desired = self._get_requirements(expected_orientation)
        vis_threshold = (
            _MIN_PARTIAL_VISIBILITY
            if expected_orientation in ("right_profile", "left_profile", "back_view")
            else _MIN_VISIBILITY
        )

        # ── Check 1: Orientation-aware body visibility ──
        missing = self._check_visibility(landmarks, essential, desired, vis_threshold)
        result.missing_groups = missing
        result.body_visible = len(missing) == 0

        if not result.body_visible:
            for group in missing:
                if group in ("nose", "head"):
                    result.guidance.append("Face the camera")
                elif "shoulder" in group:
                    result.guidance.append("Show your upper body")
                elif group in ("hips", "torso"):
                    result.guidance.append("Move backward to show your full body")
                elif group == "knees":
                    result.guidance.append("Move backward so your knees are visible")
                else:
                    result.guidance.append(f"Show your {group}")
            return result

        # ── Check 2: Body centering ──
        center_x, center_y = self._compute_body_center(landmarks, expected_orientation)
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

        # ── Check 3: Body framing (distance from camera) ──
        height_ratio = self._compute_body_height_ratio(landmarks)
        result.body_height_ratio = height_ratio
        result.body_framed = _MIN_BODY_HEIGHT_RATIO <= height_ratio <= _MAX_BODY_HEIGHT_RATIO

        if not result.body_framed:
            if height_ratio < _MIN_BODY_HEIGHT_RATIO:
                result.guidance.append("Move closer to the camera")
            elif height_ratio > _MAX_BODY_HEIGHT_RATIO:
                result.guidance.append("Move backward from the camera")

        # ── Final verdict ──
        result.is_valid = (
            result.body_visible
            and result.body_centered
            and result.body_framed
        )

        if result.is_valid and not result.guidance:
            result.guidance.append("Position looks great!")

        return result

    # ── Internal helpers ──

    def _get_requirements(
        self, orientation: Optional[str]
    ) -> tuple:
        """Return (essential, desired) landmark dicts for the orientation."""
        if orientation == "right_profile":
            return _RIGHT_ESSENTIAL, _RIGHT_DESIRED
        elif orientation == "left_profile":
            return _LEFT_ESSENTIAL, _LEFT_DESIRED
        elif orientation == "back_view":
            return _BACK_ESSENTIAL, _BACK_DESIRED
        elif orientation == "front_facing":
            return _FRONT_ESSENTIAL, _FRONT_DESIRED
        else:
            return _DEFAULT_ESSENTIAL, _DEFAULT_DESIRED

    def _check_visibility(
        self,
        landmarks: np.ndarray,
        essential: dict,
        desired: dict,
        threshold: float,
    ) -> List[str]:
        """Return names of landmark groups that are NOT sufficiently visible."""
        missing: List[str] = []

        # Essential groups — ALL landmarks in the group must be visible.
        for name, indices in essential.items():
            for idx in indices:
                if landmarks[idx, 3] < threshold:
                    missing.append(name)
                    break

        # Desired groups — at least ONE landmark in the group visible.
        for name, indices in desired.items():
            if all(landmarks[idx, 3] < threshold for idx in indices):
                missing.append(name)

        return missing

    def _compute_body_center(
        self,
        landmarks: np.ndarray,
        orientation: Optional[str] = None,
    ) -> tuple:
        """
        Compute the center of the body using available landmarks.
        Adapts to orientation — in profiles, uses whichever side
        has better visibility.
        """
        # Collect visible shoulder and hip positions.
        points = []
        for idx in [LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER, LM_LEFT_HIP, LM_RIGHT_HIP]:
            if landmarks[idx, 3] >= _MIN_PARTIAL_VISIBILITY:
                points.append(landmarks[idx, :2])

        if not points:
            return 0.5, 0.5

        coords = np.array(points)
        center_x = float(np.mean(coords[:, 0]))
        center_y = float(np.mean(coords[:, 1]))
        return center_x, center_y

    def _compute_body_height_ratio(self, landmarks: np.ndarray) -> float:
        """
        Estimate how much of the frame the body occupies vertically.
        Uses the highest and lowest visible landmark y-coordinates.
        """
        visible_mask = landmarks[:, 3] >= _MIN_PARTIAL_VISIBILITY
        if not np.any(visible_mask):
            return 0.0

        visible_y = landmarks[visible_mask, 1]
        y_min = float(np.min(visible_y))
        y_max = float(np.max(visible_y))
        return max(0.0, y_max - y_min)
