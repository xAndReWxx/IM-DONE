"""
============================================================
PhysioAI Pro V2 - Orientation Detector (Enhanced)
============================================================
PURPOSE
    Determines the user's body orientation relative to the
    camera using MediaPipe landmark analysis:
      • FRONT_FACING   — both eyes, nose centered, balanced shoulders
      • RIGHT_PROFILE  — right side dominant
      • LEFT_PROFILE   — left side dominant
      • BACK_VIEW      — nose/eyes not visible, shoulders visible
      • UNKNOWN        — can't determine orientation

TEMPORAL SMOOTHING
    Raw per-frame detection is noisy. This detector maintains
    a rolling buffer of recent detections and only confirms an
    orientation when the SAME orientation has been seen for
    N consecutive frames (default 10, reduced from 12).

BODY ROTATION ESTIMATION
    Uses shoulder depth differential and hip alignment to
    estimate body rotation angle (0° = front, ±90° = profile).
    This provides a continuous rotation signal that improves
    orientation classification, especially during transitions.

OCCLUSION-AWARE CLASSIFICATION
    The detector understands that side-profile views naturally
    hide certain landmarks. It uses MULTIPLE complementary
    signals rather than requiring all landmarks to be visible:
      1. Eye/nose/ear visibility asymmetry
      2. Shoulder apparent width (narrow = profile)
      3. Shoulder z-depth differential (rotation angle)
      4. Nose-to-shoulder lateral offset
      5. Ear visibility ratio
============================================================
"""

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)


class Orientation(str, Enum):
    FRONT_FACING = "front_facing"
    RIGHT_PROFILE = "right_profile"
    LEFT_PROFILE = "left_profile"
    BACK_VIEW = "back_view"
    UNKNOWN = "unknown"


# MediaPipe landmark indices.
LM_NOSE = 0
LM_LEFT_EYE_INNER = 1
LM_LEFT_EYE = 2
LM_LEFT_EYE_OUTER = 3
LM_RIGHT_EYE_INNER = 4
LM_RIGHT_EYE = 5
LM_RIGHT_EYE_OUTER = 6
LM_LEFT_EAR = 7
LM_RIGHT_EAR = 8
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24

# Minimum visibility for a landmark to count as "visible".
_VIS_THRESHOLD = 0.40  # Relaxed from 0.45 for profile views.
_VIS_LOW = 0.20        # Relaxed from 0.25.

# Minimum consecutive frames to confirm an orientation.
# Reduced from 12 to 10 for faster responsiveness.
_CONFIRMATION_FRAMES = 10


@dataclass
class OrientationResult:
    """Result of orientation detection for a single frame."""
    raw_orientation: Orientation = Orientation.UNKNOWN
    confirmed_orientation: Orientation = Orientation.UNKNOWN
    is_confirmed: bool = False
    confirmation_progress: float = 0.0  # 0.0 to 1.0
    confidence: float = 0.0
    rotation_angle: float = 0.0  # Estimated body rotation in degrees

    def to_dict(self) -> dict:
        return {
            "raw_orientation": self.raw_orientation.value,
            "confirmed_orientation": self.confirmed_orientation.value,
            "is_confirmed": self.is_confirmed,
            "confirmation_progress": round(self.confirmation_progress, 2),
            "confidence": round(self.confidence, 2),
            "rotation_angle": round(self.rotation_angle, 1),
        }


class OrientationDetector:
    """
    Detects body orientation with temporal smoothing and
    body rotation estimation. One instance per client.
    """

    def __init__(self, confirmation_frames: int = _CONFIRMATION_FRAMES) -> None:
        self._confirmation_frames = confirmation_frames
        self._history: deque = deque(maxlen=confirmation_frames + 5)
        self._confirmed: Orientation = Orientation.UNKNOWN
        self._consecutive_count: int = 0
        self._last_raw: Orientation = Orientation.UNKNOWN

    def detect(self, landmarks: Optional[np.ndarray]) -> OrientationResult:
        """
        Detect orientation from a single frame's landmarks.
        """
        result = OrientationResult()

        if landmarks is None or landmarks.shape[0] < 33:
            self._push(Orientation.UNKNOWN, 0.0)
            return result

        # Estimate body rotation angle.
        rotation_angle = self._estimate_rotation(landmarks)
        result.rotation_angle = rotation_angle

        # Classify using multi-signal approach.
        raw, confidence = self._classify(landmarks, rotation_angle)
        result.raw_orientation = raw
        result.confidence = confidence

        # Update temporal buffer.
        self._push(raw, confidence)

        # Check consecutive count for confirmation.
        if raw == self._last_raw and raw != Orientation.UNKNOWN:
            self._consecutive_count += 1
        else:
            self._consecutive_count = 1 if raw != Orientation.UNKNOWN else 0
            self._last_raw = raw

        progress = min(1.0, self._consecutive_count / self._confirmation_frames)
        result.confirmation_progress = progress

        if self._consecutive_count >= self._confirmation_frames:
            self._confirmed = raw
            result.is_confirmed = True
        else:
            # Also confirm if we've seen it for at least half the frames
            # AND the confirmed orientation matches.
            result.is_confirmed = (
                self._confirmed == raw and
                self._consecutive_count >= self._confirmation_frames // 2
            )

        result.confirmed_orientation = self._confirmed
        return result

    def reset(self) -> None:
        """Clear all history and confirmed state."""
        self._history.clear()
        self._confirmed = Orientation.UNKNOWN
        self._consecutive_count = 0
        self._last_raw = Orientation.UNKNOWN

    def _push(self, orientation: Orientation, confidence: float) -> None:
        self._history.append((orientation, confidence))

    def _estimate_rotation(self, lm: np.ndarray) -> float:
        """
        Estimate body rotation angle from shoulder depth differential.

        Returns degrees: 0° = facing camera, +90° = right profile,
        -90° = left profile, ±180° = back view.

        Uses the z-coordinate difference between left and right
        shoulders: when turning right, the left shoulder moves
        further from the camera (more negative z) and the right
        shoulder comes closer (less negative z).
        """
        l_sh = lm[LM_LEFT_SHOULDER]
        r_sh = lm[LM_RIGHT_SHOULDER]

        # Only use z-depth if both shoulders have reasonable visibility.
        l_vis = float(l_sh[3])
        r_vis = float(r_sh[3])

        if l_vis >= _VIS_LOW and r_vis >= _VIS_LOW:
            # z-difference: negative z = closer to camera.
            # When facing front, dz ≈ 0.
            # When showing right profile, left shoulder z << right shoulder z.
            dz = float(l_sh[2] - r_sh[2])
            # Also consider the apparent shoulder width.
            dx = abs(float(l_sh[0] - r_sh[0]))

            # Combine depth and width for rotation estimate.
            # Wider shoulders + small dz = front; narrow shoulders + large dz = profile.
            rotation_rad = np.arctan2(dz, max(dx, 0.01))
            return float(np.degrees(rotation_rad))

        # Fallback: use shoulder apparent width only.
        dx = abs(float(l_sh[0] - r_sh[0]))
        if dx < 0.06:
            # Very narrow → side profile, but can't determine which.
            return 0.0
        return 0.0

    def _classify(self, lm: np.ndarray, rotation_angle: float) -> tuple:
        """
        Classify orientation from landmark visibility, geometry,
        and estimated rotation angle.

        Returns (Orientation, confidence).
        """
        # Visibility scores for key landmarks.
        nose_vis = float(lm[LM_NOSE, 3])
        l_eye_vis = float(lm[LM_LEFT_EYE, 3])
        r_eye_vis = float(lm[LM_RIGHT_EYE, 3])
        l_ear_vis = float(lm[LM_LEFT_EAR, 3])
        r_ear_vis = float(lm[LM_RIGHT_EAR, 3])
        l_sh_vis = float(lm[LM_LEFT_SHOULDER, 3])
        r_sh_vis = float(lm[LM_RIGHT_SHOULDER, 3])

        # Shoulder apparent width.
        sh_width = abs(float(lm[LM_LEFT_SHOULDER, 0] - lm[LM_RIGHT_SHOULDER, 0]))

        # ── BACK_VIEW ──
        # Nose and both eyes not visible, but shoulders present.
        if (nose_vis < _VIS_LOW and
            l_eye_vis < _VIS_LOW and
            r_eye_vis < _VIS_LOW and
            (l_sh_vis >= _VIS_THRESHOLD or r_sh_vis >= _VIS_THRESHOLD)):
            conf = max(l_sh_vis, r_sh_vis) * 0.8
            return Orientation.BACK_VIEW, conf

        # ── FRONT_FACING ──
        both_eyes = l_eye_vis >= _VIS_THRESHOLD and r_eye_vis >= _VIS_THRESHOLD
        nose_ok = nose_vis >= _VIS_THRESHOLD
        both_sh = l_sh_vis >= _VIS_THRESHOLD and r_sh_vis >= _VIS_THRESHOLD

        if both_eyes and nose_ok and both_sh:
            # Nose should be roughly centered between shoulders.
            nose_x = float(lm[LM_NOSE, 0])
            sh_center_x = (float(lm[LM_LEFT_SHOULDER, 0]) + float(lm[LM_RIGHT_SHOULDER, 0])) / 2.0
            nose_offset = abs(nose_x - sh_center_x)

            # Ear symmetry check.
            ear_sym = abs(l_ear_vis - r_ear_vis)

            # Rotation angle should be small for front view.
            rotation_ok = abs(rotation_angle) < 25

            if nose_offset < 0.09 and ear_sym < 0.35 and rotation_ok:
                conf = min(nose_vis, l_eye_vis, r_eye_vis) * (1.0 - nose_offset * 4)
                return Orientation.FRONT_FACING, max(0.4, conf)

        # ── PROFILE detection using multi-signal approach ──

        # Signal 1: Visibility asymmetry.
        left_score = l_eye_vis + l_ear_vis + l_sh_vis
        right_score = r_eye_vis + r_ear_vis + r_sh_vis

        # Signal 2: Shoulder apparent width.
        is_narrow = sh_width < 0.13  # Profiles have narrower shoulders.

        # Signal 3: Rotation angle.
        is_rotated_right = rotation_angle > 15
        is_rotated_left = rotation_angle < -15

        # Signal 4: Single-side dominant visibility.
        right_dominant = (
            r_sh_vis >= _VIS_THRESHOLD and
            (r_ear_vis > l_ear_vis + 0.15 or l_ear_vis < _VIS_LOW)
        )
        left_dominant = (
            l_sh_vis >= _VIS_THRESHOLD and
            (l_ear_vis > r_ear_vis + 0.15 or r_ear_vis < _VIS_LOW)
        )

        # ── RIGHT_PROFILE ──
        # Right side of body faces camera. In MediaPipe coordinates,
        # right-side landmarks have higher visibility.
        right_signals = sum([
            right_score > left_score + 0.3,
            is_narrow,
            is_rotated_right,
            right_dominant,
            r_eye_vis > l_eye_vis + 0.15,
        ])

        if right_signals >= 2:
            conf = min(0.9, max(0.4, right_score / 3.0 + (0.1 * right_signals)))
            return Orientation.RIGHT_PROFILE, conf

        # ── LEFT_PROFILE ──
        left_signals = sum([
            left_score > right_score + 0.3,
            is_narrow,
            is_rotated_left,
            left_dominant,
            l_eye_vis > r_eye_vis + 0.15,
        ])

        if left_signals >= 2:
            conf = min(0.9, max(0.4, left_score / 3.0 + (0.1 * left_signals)))
            return Orientation.LEFT_PROFILE, conf

        # ── Fallback: narrow shoulders = profile ──
        if sh_width < 0.07:
            if right_score >= left_score:
                return Orientation.RIGHT_PROFILE, 0.35
            else:
                return Orientation.LEFT_PROFILE, 0.35

        # ── Fallback: probably front-facing with asymmetry ──
        if both_eyes and nose_ok:
            return Orientation.FRONT_FACING, 0.45

        # Can't determine.
        return Orientation.UNKNOWN, 0.0
