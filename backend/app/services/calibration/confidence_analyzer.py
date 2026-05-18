"""
============================================================
PhysioAI Pro V2 - Confidence Analyzer (Occlusion-Aware)
============================================================
PURPOSE
    Evaluates the overall quality / reliability of MediaPipe's
    landmark detections for the current frame. This acts as
    a gatekeeper — we don't want to capture scan data from
    frames where the model was guessing.

OCCLUSION AWARENESS
    The analyzer adapts its confidence scoring based on the
    expected orientation. During side-profile scans:
      • Only landmarks RELEVANT to the current orientation
        are weighted in the confidence score
      • Hidden landmarks on the occluded side are IGNORED
      • This prevents false "poor" grades during legitimate
        profile turns

METRICS
    1. Average visibility score across orientation-relevant landmarks
    2. Key-joint visibility (adapted per orientation)
    3. Landmark plausibility (no impossible positions)
    4. Overall confidence grade (0.0 to 1.0)

THRESHOLDS
    • confidence >= 0.65 → GOOD    (green)  — relaxed from 0.70
    • confidence >= 0.45 → FAIR    (yellow) — relaxed from 0.50
    • confidence <  0.45 → POOR    (red)
============================================================
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)


# ── Orientation-specific critical landmarks ──
# These are the landmarks we ACTUALLY care about for each orientation.

_FRONT_CRITICAL = [0, 11, 12, 23, 24]        # nose, shoulders, hips
_FRONT_IMPORTANT = [7, 8, 25, 26, 15, 16]    # ears, knees, wrists

_RIGHT_CRITICAL = [12, 24]                     # right shoulder, right hip
_RIGHT_IMPORTANT = [0, 8, 26, 16]             # nose, right ear, right knee, right wrist

_LEFT_CRITICAL = [11, 23]                      # left shoulder, left hip
_LEFT_IMPORTANT = [0, 7, 25, 15]              # nose, left ear, left knee, left wrist

_BACK_CRITICAL = [11, 12, 23, 24]             # both shoulders, both hips
_BACK_IMPORTANT = [25, 26]                     # knees

_DEFAULT_CRITICAL = _FRONT_CRITICAL
_DEFAULT_IMPORTANT = _FRONT_IMPORTANT

# Orientation → (critical, important) landmark indices.
_ORIENTATION_LANDMARKS: Dict[str, tuple] = {
    "front_facing":   (_FRONT_CRITICAL, _FRONT_IMPORTANT),
    "right_profile":  (_RIGHT_CRITICAL, _RIGHT_IMPORTANT),
    "left_profile":   (_LEFT_CRITICAL, _LEFT_IMPORTANT),
    "back_view":      (_BACK_CRITICAL, _BACK_IMPORTANT),
}

# Thresholds for grading — slightly relaxed for side profiles.
_GOOD_THRESHOLD = 0.65
_FAIR_THRESHOLD = 0.45


@dataclass
class ConfidenceResult:
    """Confidence analysis for a single frame."""
    overall_confidence: float = 0.0
    avg_visibility: float = 0.0
    critical_visibility: float = 0.0
    grade: str = "poor"  # "good" | "fair" | "poor"
    is_acceptable: bool = False
    guidance: List[str] = None

    def __post_init__(self):
        if self.guidance is None:
            self.guidance = []

    def to_dict(self) -> dict:
        return {
            "overall_confidence": round(self.overall_confidence, 3),
            "avg_visibility": round(self.avg_visibility, 3),
            "critical_visibility": round(self.critical_visibility, 3),
            "grade": self.grade,
            "is_acceptable": self.is_acceptable,
            "guidance": self.guidance,
        }


class ConfidenceAnalyzer:
    """
    Occlusion-aware confidence evaluator. Call `analyze()` per frame
    with the expected orientation to get accurate confidence scoring
    that doesn't penalize expected occlusion.
    """

    def analyze(
        self,
        landmarks: Optional[np.ndarray],
        expected_orientation: Optional[str] = None,
    ) -> ConfidenceResult:
        """
        Evaluate confidence of the current landmark detection.

        Args:
            landmarks: (33, 4) array or None.
            expected_orientation: "front_facing", "right_profile",
                "left_profile", "back_view", or None.

        Returns:
            ConfidenceResult with scores and guidance.
        """
        result = ConfidenceResult()

        if landmarks is None or landmarks.shape[0] < 33:
            result.guidance.append("No landmarks detected")
            return result

        # Get orientation-specific landmark sets.
        critical_indices, important_indices = _ORIENTATION_LANDMARKS.get(
            expected_orientation or "front_facing",
            (_DEFAULT_CRITICAL, _DEFAULT_IMPORTANT),
        )

        # Compute visibility scores for orientation-relevant landmarks only.
        critical_vis = np.array([landmarks[i, 3] for i in critical_indices])
        result.critical_visibility = float(np.mean(critical_vis))

        important_vis = np.array([landmarks[i, 3] for i in important_indices])
        important_avg = float(np.mean(important_vis))

        # Average visibility across ALL relevant landmarks (not all 33).
        all_relevant = list(set(critical_indices + important_indices))
        relevant_vis = np.array([landmarks[i, 3] for i in all_relevant])
        result.avg_visibility = float(np.mean(relevant_vis))

        # Plausibility check: relevant landmarks should be in bounds.
        relevant_xy = landmarks[all_relevant, :2]
        in_bounds = np.all((relevant_xy >= -0.15) & (relevant_xy <= 1.15))
        plausibility_bonus = 0.1 if in_bounds else -0.1

        # Compute overall confidence as weighted combination.
        # Critical landmarks are weighted more heavily.
        result.overall_confidence = float(np.clip(
            0.45 * result.critical_visibility +
            0.25 * result.avg_visibility +
            0.15 * important_avg +
            0.15 + plausibility_bonus,  # base + bonus
            0.0, 1.0,
        ))

        # Grade assignment.
        if result.overall_confidence >= _GOOD_THRESHOLD:
            result.grade = "good"
            result.is_acceptable = True
        elif result.overall_confidence >= _FAIR_THRESHOLD:
            result.grade = "fair"
            result.is_acceptable = True
            result.guidance.append("Detection quality is fair. Better lighting may help.")
        else:
            result.grade = "poor"
            result.is_acceptable = False

            # Specific guidance based on what's low.
            if result.critical_visibility < 0.4:
                if expected_orientation in ("right_profile", "left_profile"):
                    side = "right" if expected_orientation == "right_profile" else "left"
                    result.guidance.append(
                        f"Your {side} side is hard to see. Adjust your position."
                    )
                else:
                    result.guidance.append("Key joints are hard to see. Face the camera.")
            if result.avg_visibility < 0.3:
                result.guidance.append("Improve lighting conditions")
            if not in_bounds:
                result.guidance.append("Some body parts are out of frame")

        return result
