"""
============================================================
PhysioAI Pro V2 - Landmark Smoothing (EMA + Predictive)
============================================================
PURPOSE
    MediaPipe landmarks jitter slightly frame-to-frame, which
    produces a "shaky" skeleton overlay and noisy angle readings
    that flip between "good" and "bad" posture each frame.

    An Exponential Moving Average (EMA) blends each new value
    with the running state:
        state = α * new + (1 − α) * state
    Higher α  → more responsive, less smooth.
    Lower  α  → smoother, more lag.

PREDICTIVE TRACKING
    When a landmark temporarily disappears (e.g. arm behind
    body during a side-profile turn), the filter:
      1. Predicts the position from the last two frames' velocity
      2. Decays the visibility score exponentially
      3. Maintains tracking continuity for up to N frames
    This prevents scan failure when occlusion is expected.

OCCLUSION AWARENESS
    During side-profile scans, certain landmarks naturally
    become invisible. The filter tracks which landmarks are
    "expected occluded" and uses prediction to fill gaps
    instead of resetting the filter state.

CHANGE 6 — Increased temporal smoothing + angle smoothing buffer:
    • Default alpha raised to 0.35 (was 0.5) for a more stable
      skeleton at 20 FPS.
    • An angle buffer (last 5 frames) can be fed via
      `smooth_angles()` to further reduce jitter in computed
      angles before they reach the posture analyzer.
============================================================
"""

from collections import deque
from typing import Deque, Dict, Optional
import numpy as np


# Maximum frames to predict a landmark before giving up.
_MAX_PREDICTION_FRAMES = 8

# Per-frame visibility decay when predicting.
_VISIBILITY_DECAY = 0.85

# Minimum visibility to consider a landmark "trackable" for prediction.
_MIN_TRACKABLE_VISIBILITY = 0.2


class LandmarkFilter:
    """
    Smooths a (33, 4) array of [x, y, z, visibility] over time.
    Now includes predictive tracking for temporarily occluded landmarks.

    Each connection has its own LandmarkFilter so users don't
    contaminate each other's smoothing state.
    """

    ANGLE_BUFFER_LEN = 5  # moving average window for angle smoothing

    def __init__(self, alpha: float = 0.35):
        # alpha=0.35 gives more smoothing than the previous 0.5 default
        # while keeping responsive enough at ~20 FPS.
        self.alpha = float(alpha)
        self._state: Optional[np.ndarray] = None
        # Per-angle moving average buffers: {angle_name: deque of floats}
        self._angle_buffers: Dict[str, Deque[float]] = {}

        # Predictive tracking state.
        self._prev_state: Optional[np.ndarray] = None      # t-1
        self._prediction_counts: Optional[np.ndarray] = None  # per-landmark prediction counter
        self._velocity: Optional[np.ndarray] = None         # estimated velocity

    def filter(self, landmarks: np.ndarray) -> np.ndarray:
        """
        Apply EMA with predictive tracking for occluded landmarks.

        For each landmark:
          - If visibility >= threshold: normal EMA update
          - If visibility < threshold AND we have history:
            predict position from velocity, decay visibility
          - Reset prediction counter when landmark reappears
        """
        if self._state is None or self._state.shape != landmarks.shape:
            self._state = landmarks.copy()
            self._prev_state = landmarks.copy()
            self._prediction_counts = np.zeros(landmarks.shape[0], dtype=np.int32)
            self._velocity = np.zeros_like(landmarks[:, :3])
            return self._state

        result = np.copy(landmarks)
        n_landmarks = landmarks.shape[0]

        for i in range(n_landmarks):
            current_vis = float(landmarks[i, 3])
            state_vis = float(self._state[i, 3])

            if current_vis >= _MIN_TRACKABLE_VISIBILITY:
                # Landmark is visible — normal EMA update.
                result[i] = self.alpha * landmarks[i] + (1.0 - self.alpha) * self._state[i]

                # Update velocity estimate from actual movement.
                self._velocity[i] = landmarks[i, :3] - self._state[i, :3]
                self._prediction_counts[i] = 0

            elif (state_vis >= _MIN_TRACKABLE_VISIBILITY and
                  self._prediction_counts[i] < _MAX_PREDICTION_FRAMES):
                # Landmark just disappeared — predict from velocity.
                predicted_pos = self._state[i, :3] + self._velocity[i] * 0.5
                predicted_vis = state_vis * _VISIBILITY_DECAY

                result[i, :3] = predicted_pos
                result[i, 3] = predicted_vis

                # Dampen velocity over time.
                self._velocity[i] *= 0.7
                self._prediction_counts[i] += 1
            else:
                # Landmark has been gone too long — use raw (low-vis) value.
                result[i] = landmarks[i]
                self._prediction_counts[i] = 0

        # Store for next frame.
        self._prev_state = self._state.copy()
        self._state = result.copy()

        return result

    def smooth_angles(self, angles: Dict[str, float]) -> Dict[str, float]:
        """
        Apply a simple moving average over the last N frames for each
        named angle. Reduces high-frequency jitter in posture readings
        without introducing the latency of a longer EMA.

        Args:
            angles: dict of {angle_name: value_degrees}

        Returns:
            New dict with each angle replaced by its N-frame mean.
        """
        smoothed: Dict[str, float] = {}
        for name, value in angles.items():
            buf = self._angle_buffers.get(name)
            if buf is None:
                buf = deque(maxlen=self.ANGLE_BUFFER_LEN)
                self._angle_buffers[name] = buf
            buf.append(value)
            smoothed[name] = float(np.mean(buf))
        return smoothed

    def reset(self) -> None:
        """Clear smoothing history — useful when the user re-frames the camera."""
        self._state = None
        self._prev_state = None
        self._prediction_counts = None
        self._velocity = None
        self._angle_buffers.clear()

    def get_prediction_status(self) -> Optional[np.ndarray]:
        """
        Returns per-landmark prediction counts (0 = real data,
        >0 = predicted for N frames). Useful for diagnostics.
        """
        return self._prediction_counts
