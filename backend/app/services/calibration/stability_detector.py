"""
============================================================
PhysioAI Pro V2 - Stability Detector
============================================================
PURPOSE
    Determines whether the user is standing still enough for
    a reliable scan capture. Uses a rolling window of recent
    landmark positions to compute:
      1. Per-landmark motion variance
      2. Average velocity across key joints
      3. Overall stability score (0.0 = chaotic, 1.0 = frozen)

    The user must maintain stability above a threshold for
    a minimum number of consecutive frames before the scan
    can capture.

ALGORITHM
    For each frame, we store the positions of key landmarks
    (shoulders, hips, nose). We compute:
      • Frame-to-frame displacement for each landmark
      • Exponentially weighted moving average of displacement
      • Stability score = 1.0 - clamp(avg_displacement / max_allowed)

    The score naturally smooths out micro-jitter while still
    catching deliberate movements.
============================================================
"""

from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)


# Key landmarks to track for stability (we don't need all 33).
_STABILITY_LANDMARKS = [
    0,   # nose
    11,  # left_shoulder
    12,  # right_shoulder
    23,  # left_hip
    24,  # right_hip
]

# Rolling window size for stability computation.
_WINDOW_SIZE = 20

# Maximum allowed average displacement (normalized coords) per frame
# before stability is considered "bad". 0.008 ≈ less than 1% of frame.
_MAX_DISPLACEMENT = 0.008

# Minimum stability score (0–1) to consider "stable".
_STABILITY_THRESHOLD = 0.75

# Minimum consecutive stable frames to confirm stability.
_STABLE_FRAME_COUNT = 10

# EMA alpha for smoothing the stability score.
_EMA_ALPHA = 0.3


@dataclass
class StabilityResult:
    """Result of stability analysis for a single frame."""
    is_stable: bool = False
    stability_score: float = 0.0       # 0.0 (moving) to 1.0 (still)
    avg_displacement: float = 0.0      # average per-frame displacement
    consecutive_stable: int = 0        # frames stable in a row
    stability_confirmed: bool = False  # stable for long enough?

    def to_dict(self) -> dict:
        return {
            "is_stable": self.is_stable,
            "stability_score": round(self.stability_score, 3),
            "avg_displacement": round(self.avg_displacement, 5),
            "consecutive_stable": self.consecutive_stable,
            "stability_confirmed": self.stability_confirmed,
        }


class StabilityDetector:
    """
    Tracks body stability over time. One instance per client.
    """

    def __init__(
        self,
        window_size: int = _WINDOW_SIZE,
        threshold: float = _STABILITY_THRESHOLD,
        required_frames: int = _STABLE_FRAME_COUNT,
    ) -> None:
        self._window_size = window_size
        self._threshold = threshold
        self._required_frames = required_frames

        # Rolling buffer of key landmark positions.
        self._position_buffer: deque = deque(maxlen=window_size)
        self._displacement_buffer: deque = deque(maxlen=window_size)

        # Smoothed stability score.
        self._smoothed_score: float = 0.0
        self._consecutive_stable: int = 0

    def update(self, landmarks: Optional[np.ndarray]) -> StabilityResult:
        """
        Process one frame of landmarks and return stability status.

        Args:
            landmarks: (33, 4) array or None.

        Returns:
            StabilityResult with stability score and confirmation.
        """
        result = StabilityResult()

        if landmarks is None or landmarks.shape[0] < 33:
            # Lost tracking — reset stability.
            self._consecutive_stable = 0
            self._smoothed_score *= 0.5  # Decay toward 0.
            result.stability_score = self._smoothed_score
            return result

        # Extract key landmark positions (x, y only).
        current_positions = np.array(
            [landmarks[idx, :2] for idx in _STABILITY_LANDMARKS],
            dtype=np.float64,
        )

        if len(self._position_buffer) > 0:
            prev_positions = self._position_buffer[-1]
            displacements = np.linalg.norm(current_positions - prev_positions, axis=1)
            avg_disp = float(np.mean(displacements))
            self._displacement_buffer.append(avg_disp)
        else:
            avg_disp = 0.0

        self._position_buffer.append(current_positions)

        # Compute stability score from recent displacements.
        if len(self._displacement_buffer) > 0:
            recent_avg = float(np.mean(list(self._displacement_buffer)))
            raw_score = max(0.0, 1.0 - (recent_avg / _MAX_DISPLACEMENT))
        else:
            raw_score = 0.5  # Not enough data yet.

        # EMA smoothing.
        self._smoothed_score = (
            _EMA_ALPHA * raw_score + (1 - _EMA_ALPHA) * self._smoothed_score
        )

        result.stability_score = self._smoothed_score
        result.avg_displacement = avg_disp
        result.is_stable = self._smoothed_score >= self._threshold

        # Track consecutive stable frames.
        if result.is_stable:
            self._consecutive_stable += 1
        else:
            self._consecutive_stable = 0

        result.consecutive_stable = self._consecutive_stable
        result.stability_confirmed = self._consecutive_stable >= self._required_frames

        return result

    def reset(self) -> None:
        """Clear all history."""
        self._position_buffer.clear()
        self._displacement_buffer.clear()
        self._smoothed_score = 0.0
        self._consecutive_stable = 0
