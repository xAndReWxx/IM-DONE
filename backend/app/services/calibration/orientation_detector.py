"""
============================================================
PhysioAI Pro V2 - Orientation Detector
============================================================
PURPOSE
    Determines the user's body orientation relative to the
    camera using MediaPipe landmark analysis:
      • FRONT_FACING   — both eyes, nose centered, balanced shoulders
      • RIGHT_PROFILE  — right side dominant, nose shifted left
      • LEFT_PROFILE   — left side dominant, nose shifted right
      • BACK_VIEW      — nose/eyes not visible, shoulders visible
      • UNKNOWN        — can't determine orientation

TEMPORAL SMOOTHING
    Raw per-frame detection is noisy. This detector maintains
    a rolling buffer of recent detections and only confirms an
    orientation when the SAME orientation has been seen for
    N consecutive frames (default 12). This prevents flickering
    during transitions.

DETECTION STRATEGY
    Uses multiple complementary signals:
      1. Eye/nose/ear visibility patterns
      2. Shoulder width ratio (front vs profile)
      3. Nose-to-shoulder lateral offset
      4. Ear visibility asymmetry
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
_VIS_THRESHOLD = 0.45
_VIS_LOW = 0.25

# Minimum consecutive frames to confirm an orientation.
_CONFIRMATION_FRAMES = 12

# Shoulder width ratio threshold: front view has wider shoulders
# than profile view. If the ratio of apparent shoulder width to
# hip width is below this, it's likely a profile.
_SHOULDER_NARROW_RATIO = 0.55


@dataclass
class OrientationResult:
    """Result of orientation detection for a single frame."""
    raw_orientation: Orientation = Orientation.UNKNOWN
    confirmed_orientation: Orientation = Orientation.UNKNOWN
    is_confirmed: bool = False
    confirmation_progress: float = 0.0  # 0.0 to 1.0
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "raw_orientation": self.raw_orientation.value,
            "confirmed_orientation": self.confirmed_orientation.value,
            "is_confirmed": self.is_confirmed,
            "confirmation_progress": round(self.confirmation_progress, 2),
            "confidence": round(self.confidence, 2),
        }


class OrientationDetector:
    """
    Detects body orientation with temporal smoothing.
    Maintains per-instance state (rolling buffer), so create
    one per client.
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

        Args:
            landmarks: (33, 4) array or None.

        Returns:
            OrientationResult with raw and confirmed orientation.
        """
        result = OrientationResult()

        if landmarks is None or landmarks.shape[0] < 33:
            self._push(Orientation.UNKNOWN, 0.0)
            return result

        # Detect raw orientation from landmark patterns.
        raw, confidence = self._classify(landmarks)
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
            result.is_confirmed = (self._confirmed == raw and
                                   self._consecutive_count >= self._confirmation_frames // 2)

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

    def _classify(self, lm: np.ndarray) -> tuple:
        """
        Classify orientation from landmark visibility and geometry.
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

        # ── BACK_VIEW ──
        # If nose and both eyes are not visible but shoulders are.
        if (nose_vis < _VIS_LOW and
            l_eye_vis < _VIS_LOW and
            r_eye_vis < _VIS_LOW and
            l_sh_vis >= _VIS_THRESHOLD and
            r_sh_vis >= _VIS_THRESHOLD):
            conf = min(l_sh_vis, r_sh_vis)
            return Orientation.BACK_VIEW, conf

        # ── FRONT_FACING ──
        # Both eyes visible, nose visible, shoulders visible.
        both_eyes = l_eye_vis >= _VIS_THRESHOLD and r_eye_vis >= _VIS_THRESHOLD
        nose_ok = nose_vis >= _VIS_THRESHOLD
        both_sh = l_sh_vis >= _VIS_THRESHOLD and r_sh_vis >= _VIS_THRESHOLD

        if both_eyes and nose_ok and both_sh:
            # Additional check: shoulder width symmetry.
            # In front view, the x-distance between shoulders is wider.
            sh_width = abs(float(lm[LM_LEFT_SHOULDER, 0] - lm[LM_RIGHT_SHOULDER, 0]))
            hip_width = abs(float(lm[LM_LEFT_HIP, 0] - lm[LM_RIGHT_HIP, 0]))

            # Nose should be roughly centered between shoulders.
            nose_x = float(lm[LM_NOSE, 0])
            sh_center_x = (float(lm[LM_LEFT_SHOULDER, 0]) + float(lm[LM_RIGHT_SHOULDER, 0])) / 2.0
            nose_offset = abs(nose_x - sh_center_x)

            # Ear symmetry.
            ear_sym = abs(l_ear_vis - r_ear_vis)

            # Front facing if nose is centered and ears are symmetric.
            if nose_offset < 0.08 and ear_sym < 0.3:
                conf = min(nose_vis, l_eye_vis, r_eye_vis) * (1.0 - nose_offset * 5)
                return Orientation.FRONT_FACING, max(0.3, conf)

        # ── PROFILE detection ──
        # Look at which side's landmarks are more visible.

        # Compute left-side vs right-side visibility score.
        left_score = l_eye_vis + l_ear_vis + l_sh_vis
        right_score = r_eye_vis + r_ear_vis + r_sh_vis

        # Shoulder apparent width — profiles have narrower apparent shoulders.
        sh_width = abs(float(lm[LM_LEFT_SHOULDER, 0] - lm[LM_RIGHT_SHOULDER, 0]))

        # Nose position relative to shoulder center.
        nose_x = float(lm[LM_NOSE, 0])
        sh_center_x = (float(lm[LM_LEFT_SHOULDER, 0]) + float(lm[LM_RIGHT_SHOULDER, 0])) / 2.0

        # RIGHT_PROFILE: user's right side faces camera.
        # In mirrored camera view, the right side of the body appears
        # on the LEFT side of the screen. But we work in normalized
        # landmark coordinates where x increases left→right.
        # When showing right profile, left-side landmarks (camera's right)
        # tend to be more visible.
        if right_score > left_score + 0.5 or (
            r_ear_vis > l_ear_vis + 0.2 and
            r_eye_vis > l_eye_vis + 0.15 and
            sh_width < 0.15
        ):
            conf = min(0.9, right_score / 3.0)
            return Orientation.RIGHT_PROFILE, conf

        # LEFT_PROFILE: mirror of right.
        if left_score > right_score + 0.5 or (
            l_ear_vis > r_ear_vis + 0.2 and
            l_eye_vis > r_eye_vis + 0.15 and
            sh_width < 0.15
        ):
            conf = min(0.9, left_score / 3.0)
            return Orientation.LEFT_PROFILE, conf

        # ── Fallback: use shoulder width as disambiguator ──
        if sh_width < 0.08:
            # Very narrow shoulders → likely a profile.
            if right_score >= left_score:
                return Orientation.RIGHT_PROFILE, 0.4
            else:
                return Orientation.LEFT_PROFILE, 0.4

        # Can't determine.
        if both_eyes and nose_ok:
            # Probably front-facing but with some asymmetry.
            return Orientation.FRONT_FACING, 0.5

        return Orientation.UNKNOWN, 0.0
