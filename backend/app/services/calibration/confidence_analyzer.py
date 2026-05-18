"""
============================================================
PhysioAI Pro V2 - Confidence Analyzer (Front-Only)
============================================================
PURPOSE
    Evaluates the quality of MediaPipe's landmark detections.
    Gates scan capture — we only capture when confidence is
    acceptable. Front-facing landmarks only.

THRESHOLDS
    • confidence >= 0.65 → GOOD  (green)
    • confidence >= 0.45 → FAIR  (yellow)
    • confidence <  0.45 → POOR  (red)
============================================================
"""

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Front-facing critical landmarks: nose, shoulders, hips.
_CRITICAL = [0, 11, 12, 23, 24]
# Important but not critical: ears, knees, wrists.
_IMPORTANT = [7, 8, 25, 26, 15, 16]

_GOOD_THRESHOLD = 0.65
_FAIR_THRESHOLD = 0.45


@dataclass
class ConfidenceResult:
    """Confidence analysis for a single frame."""
    overall_confidence: float = 0.0
    avg_visibility: float = 0.0
    grade: str = "poor"
    is_acceptable: bool = False
    guidance: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_confidence": round(self.overall_confidence, 3),
            "avg_visibility": round(self.avg_visibility, 3),
            "grade": self.grade,
            "is_acceptable": self.is_acceptable,
            "guidance": self.guidance,
        }


class ConfidenceAnalyzer:
    """Front-facing confidence evaluator."""

    def analyze(self, landmarks: Optional[np.ndarray]) -> ConfidenceResult:
        """
        Evaluate confidence of landmark detection.

        Args:
            landmarks: (33, 4) array or None.

        Returns:
            ConfidenceResult with scores and guidance.
        """
        result = ConfidenceResult()

        if landmarks is None or landmarks.shape[0] < 33:
            result.guidance.append("No landmarks detected")
            return result

        # Critical landmark visibility.
        critical_vis = np.array([landmarks[i, 3] for i in _CRITICAL])
        critical_avg = float(np.mean(critical_vis))

        # Important landmark visibility.
        important_vis = np.array([landmarks[i, 3] for i in _IMPORTANT])
        important_avg = float(np.mean(important_vis))

        # Overall visibility.
        all_indices = list(set(_CRITICAL + _IMPORTANT))
        all_vis = np.array([landmarks[i, 3] for i in all_indices])
        result.avg_visibility = float(np.mean(all_vis))

        # Plausibility: landmarks should be in reasonable bounds.
        relevant_xy = landmarks[all_indices, :2]
        in_bounds = bool(np.all((relevant_xy >= -0.15) & (relevant_xy <= 1.15)))
        plausibility_bonus = 0.1 if in_bounds else -0.1

        # Weighted confidence score.
        result.overall_confidence = float(np.clip(
            0.45 * critical_avg +
            0.25 * result.avg_visibility +
            0.15 * important_avg +
            0.15 + plausibility_bonus,
            0.0, 1.0,
        ))

        # Grade.
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
            if critical_avg < 0.4:
                result.guidance.append("Key joints are hard to see. Face the camera.")
            if result.avg_visibility < 0.3:
                result.guidance.append("Improve lighting conditions")
            if not in_bounds:
                result.guidance.append("Some body parts are out of frame")

        return result
