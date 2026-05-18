"""
============================================================
PhysioAI Pro V2 - Realtime Motion Tracker
============================================================
PURPOSE
    Per-client realtime engine that:
      1. Accumulates user landmark frames during exercise
      2. Detects rep boundaries in the live stream
      3. Compares each rep against the loaded MotionTemplate
      4. Generates quality scores and corrections
      5. Counts reps automatically

    Replaces the simple angle-threshold trackers when a
    MotionTemplate is available. Falls back gracefully to
    heuristic tracking if no template is loaded.

INTEGRATION
    The AIEngine creates one RealtimeMotionTracker per client
    when an exercise is selected AND a MotionTemplate exists.
    It calls `tracker.process(landmarks)` each frame, getting
    back a MotionTrackingResult.
============================================================
"""

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from app.services.ai.geometry import calculate_angle
from app.services.exercise_engine.dtw_comparator import (
    compare_to_template,
    ComparisonResult,
)
from app.services.exercise_engine.motion_template import (
    MotionTemplate,
    CANONICAL_REP_STEPS,
)
from app.services.exercise_engine.phase_detector import (
    EXERCISE_ANGLES,
    DEFAULT_ANGLES,
    PhaseLabel,
)
from app.services.exercise_engine.feedback_throttler import FeedbackThrottler
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Minimum frames to consider a rep.
MIN_REP_FRAMES = 8
# How many frames of angle history to keep for live analysis.
MAX_HISTORY_FRAMES = 600  # ~20 seconds at 30fps


@dataclass
class MotionTrackingResult:
    """Per-frame output from the RealtimeMotionTracker."""
    reps: int = 0
    phase: str = "rest"
    quality_score: int = 0
    similarity: float = 0.0
    correction: Optional[str] = None
    feedback_ar: str = ""
    range_score: float = 0.0
    timing_score: float = 0.0


class RealtimeMotionTracker:
    """
    Live exercise tracker powered by DTW comparison against
    a MotionTemplate reference.
    """

    def __init__(
        self,
        template: MotionTemplate,
        fps: float = 15.0,
    ) -> None:
        self._template = template
        self._fps = fps
        self._throttler = FeedbackThrottler()

        # Angle definitions for this exercise.
        self._angle_defs = EXERCISE_ANGLES.get(
            template.exercise_id, DEFAULT_ANGLES
        )
        self._n_angles = len(self._angle_defs)

        # Rolling history: angle_history (n_angles, frames), landmark_history (frames, 33, 4)
        self._angle_history: List[np.ndarray] = []
        self._landmark_history: List[np.ndarray] = []

        # State tracking.
        self._reps = 0
        self._current_phase = PhaseLabel.REST
        self._last_comparison: Optional[ComparisonResult] = None
        self._last_quality_score = 0

        # Rep detection: track signal peaks/valleys in real time.
        self._signal_history: List[float] = []
        self._signal_baseline: Optional[float] = None
        self._in_rep = False
        self._rep_start_frame = 0
        self._peak_value = 0.0
        self._valley_value = float("inf")

        # Adaptive thresholds (learned from template).
        ref_signal = template.canonical_angles[0] if template.canonical_angles.shape[0] > 0 else np.zeros(100)
        self._ref_range = float(np.max(ref_signal) - np.min(ref_signal))
        self._threshold = max(3.0, self._ref_range * 0.3)

    @property
    def reps(self) -> int:
        return self._reps

    @property
    def phase(self) -> str:
        return self._current_phase.value

    def reset(self) -> None:
        """Reset rep counter and history."""
        self._reps = 0
        self._angle_history.clear()
        self._landmark_history.clear()
        self._signal_history.clear()
        self._in_rep = False
        self._signal_baseline = None
        self._last_comparison = None
        self._last_quality_score = 0
        self._throttler.reset()

    def process(self, landmarks: np.ndarray) -> MotionTrackingResult:
        """
        Process one frame of landmarks.
        Returns the current tracking state.
        """
        result = MotionTrackingResult(
            reps=self._reps,
            phase=self._current_phase.value,
            quality_score=self._last_quality_score,
        )

        if landmarks is None or landmarks.shape[0] < 33:
            return result

        # ── Compute angles for this frame ──
        frame_angles = np.zeros(self._n_angles, dtype=np.float64)
        for j, (a_idx, b_idx, c_idx) in enumerate(self._angle_defs):
            frame_angles[j] = calculate_angle(
                landmarks[a_idx, :2],
                landmarks[b_idx, :2],
                landmarks[c_idx, :2],
            )

        self._angle_history.append(frame_angles)
        self._landmark_history.append(landmarks)

        # Trim history to prevent unbounded growth.
        if len(self._angle_history) > MAX_HISTORY_FRAMES:
            self._angle_history = self._angle_history[-MAX_HISTORY_FRAMES:]
            self._landmark_history = self._landmark_history[-MAX_HISTORY_FRAMES:]

        # ── Motion signal (average of angles) ──
        signal_value = float(np.mean(frame_angles))
        self._signal_history.append(signal_value)

        # Learn baseline from first frames.
        if self._signal_baseline is None and len(self._signal_history) >= 5:
            self._signal_baseline = np.mean(self._signal_history[:5])

        # ── Real-time rep detection ──
        if self._signal_baseline is not None:
            deviation = abs(signal_value - self._signal_baseline)

            if not self._in_rep:
                # Waiting for movement to start.
                if deviation > self._threshold:
                    self._in_rep = True
                    self._rep_start_frame = len(self._angle_history) - 1
                    self._peak_value = signal_value
                    self._valley_value = signal_value
                    self._current_phase = PhaseLabel.CONCENTRIC
                    result.phase = self._current_phase.value
                    result.feedback_ar = "ممتاز، استمر"
            else:
                # Track peak/valley during rep.
                if signal_value > self._peak_value:
                    self._peak_value = signal_value
                    self._current_phase = PhaseLabel.CONCENTRIC
                elif signal_value < self._valley_value:
                    self._valley_value = signal_value

                # Check if user has returned to near baseline.
                if deviation < self._threshold * 0.5:
                    # Rep complete!
                    rep_end = len(self._angle_history) - 1
                    rep_len = rep_end - self._rep_start_frame

                    if rep_len >= MIN_REP_FRAMES:
                        self._reps += 1
                        self._current_phase = PhaseLabel.REST

                        # ── Compare this rep against template ──
                        comparison = self._compare_current_rep(
                            self._rep_start_frame, rep_end
                        )
                        if comparison:
                            self._last_comparison = comparison
                            self._last_quality_score = comparison.quality_score
                            result.quality_score = comparison.quality_score
                            result.similarity = comparison.overall_similarity
                            result.range_score = comparison.range_score
                            result.timing_score = comparison.timing_score

                            # Throttled correction.
                            if comparison.corrections:
                                for corr in comparison.corrections:
                                    allowed = self._throttler.try_send(corr)
                                    if allowed:
                                        result.correction = corr
                                        break

                        result.feedback_ar = f"{self._reps} — ممتاز"

                    self._in_rep = False
                    self._peak_value = 0.0
                    self._valley_value = float("inf")

                # Phase detection during rep.
                elif self._current_phase == PhaseLabel.CONCENTRIC:
                    # If signal starts decreasing, we're at peak → eccentric.
                    if len(self._signal_history) >= 3:
                        recent = self._signal_history[-3:]
                        if recent[-1] < recent[-2] < recent[-3]:
                            self._current_phase = PhaseLabel.ECCENTRIC
                            result.feedback_ar = "عُد ببطء"

        result.reps = self._reps
        result.phase = self._current_phase.value

        return result

    def _compare_current_rep(
        self,
        start_frame: int,
        end_frame: int,
    ) -> Optional[ComparisonResult]:
        """
        Compare a completed rep against the template.
        """
        try:
            rep_data = self._angle_history[start_frame:end_frame + 1]
            rep_landmarks_data = self._landmark_history[start_frame:end_frame + 1]
            
            if len(rep_data) < MIN_REP_FRAMES:
                return None

            # Stack into (n_angles, rep_len) array.
            rep_array = np.array(rep_data).T  # (n_angles, rep_len)
            rep_landmarks = np.array(rep_landmarks_data) # (rep_len, 33, 4)

            # Resample angles to CANONICAL_REP_STEPS for fair comparison.
            n_angles = min(rep_array.shape[0], self._template.canonical_angles.shape[0])
            user_resampled = np.zeros((n_angles, CANONICAL_REP_STEPS))
            for i in range(n_angles):
                x_old = np.linspace(0, 1, rep_array.shape[1])
                x_new = np.linspace(0, 1, CANONICAL_REP_STEPS)
                user_resampled[i] = np.interp(x_new, x_old, rep_array[i])

            # Resample landmarks to CANONICAL_REP_STEPS (33, 4, CANONICAL_REP_STEPS)
            user_landmarks_resampled = np.zeros((33, 4, CANONICAL_REP_STEPS))
            for lm_idx in range(33):
                for coord in range(4):
                    curve = rep_landmarks[:, lm_idx, coord]
                    user_landmarks_resampled[lm_idx, coord] = np.interp(x_new, x_old, curve)

            return compare_to_template(
                exercise_id=self._template.exercise_id,
                user_angle_curves=user_resampled,
                template_canonical=self._template.canonical_angles[:n_angles],
                template_angle_ranges=self._template.angle_ranges,
                template_angle_names=self._template.angle_names,
                user_landmarks=user_landmarks_resampled,
                template_landmarks=self._template.canonical_landmarks,
                user_fps=self._fps,
                template_fps=self._template.source_fps,
            )
        except Exception as e:
            logger.warning("rep_comparison_failed", error=str(e))
            return None

    def to_rep_state_dict(self) -> dict:
        """
        Serialize state compatible with the RepState wire format +
        motion quality extensions.
        """
        return {
            "exercise_id": self._template.exercise_id,
            "reps": self._reps,
            "phase": self._current_phase.value,
            "last_feedback_ar": f"{self._reps} — ممتاز" if self._reps > 0 else "استعداد",
            "quality_score": self._last_quality_score,
            "similarity": round(self._last_comparison.overall_similarity, 2)
                if self._last_comparison else 0.0,
        }
