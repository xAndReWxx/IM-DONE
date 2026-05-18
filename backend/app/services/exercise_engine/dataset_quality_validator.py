"""
============================================================
PhysioAI Pro V2 - Dataset Quality Validator
============================================================
PURPOSE
    Validates generated motion datasets to ensure they meet
    production quality standards. Rejects datasets with poor
    tracking, high failure rates, or excessive jitter.

METRICS
    - detection_success_rate: % of frames where MediaPipe succeeded
    - visibility_score: average visibility confidence of key joints
    - stability_score: absence of unnatural high-frequency jitter
    - continuity_score: lack of large gaps in tracking
    - motion_smoothness: overall kinematic smoothness

OUTPUT
    ValidationResult with boolean `is_valid` and reason if failed.
============================================================
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationMetrics:
    detection_success_rate: float
    visibility_score: float
    stability_score: float
    continuity_score: float
    smoothness_score: float


@dataclass
class ValidationResult:
    is_valid: bool
    metrics: ValidationMetrics
    failure_reasons: List[str]


def validate_dataset(
    raw_landmarks: np.ndarray,
    valid_mask: np.ndarray,
    normalized_landmarks: np.ndarray,
) -> ValidationResult:
    """
    Validate a dataset before generating templates/exports.

    Args:
        raw_landmarks: (N, 33, 4) raw landmarks from MediaPipe
        valid_mask: (N,) boolean array of successful detections
        normalized_landmarks: (N, 33, 4) smoothed & normalized
    """
    reasons = []
    n_frames = len(valid_mask)

    if n_frames < 30:
        return ValidationResult(
            is_valid=False,
            metrics=ValidationMetrics(0, 0, 0, 0, 0),
            failure_reasons=["Dataset too short (under 30 frames)"],
        )

    # 1. Detection Success Rate
    success_rate = float(np.mean(valid_mask))
    if success_rate < 0.35:
        reasons.append(f"Detection success rate too low: {success_rate:.1%}")

    # 2. Continuity (Max gap size)
    # Find the largest contiguous block of False in valid_mask
    invalid_indices = np.where(~valid_mask)[0]
    max_gap = 0
    if len(invalid_indices) > 0:
        gaps = np.diff(invalid_indices)
        # diff(invalid_indices) == 1 means adjacent failed frames.
        # To find actual max gap length, we can split by diff > 1.
        if len(gaps) > 0:
            blocks = np.split(invalid_indices, np.where(gaps > 1)[0] + 1)
            max_gap = max(len(b) for b in blocks)
        else:
            max_gap = 1

    continuity_score = max(0.0, 1.0 - (max_gap / max(1, n_frames * 0.1)))
    if max_gap > max(15, n_frames * 0.15):
        reasons.append(f"Large tracking gap detected: {max_gap} consecutive failed frames")

    # 3. Visibility Score (average visibility of upper body joints)
    # Joints: shoulders (11,12), elbows (13,14), wrists (15,16)
    upper_joints = [11, 12, 13, 14, 15, 16]
    valid_raw = raw_landmarks[valid_mask]
    if len(valid_raw) > 0:
        vis_values = valid_raw[:, upper_joints, 3]
        visibility_score = float(np.mean(vis_values))
    else:
        visibility_score = 0.0

    if visibility_score < 0.5:
        reasons.append(f"Average upper body visibility too low: {visibility_score:.2f}")

    # 4. Stability (Jitter before smoothing)
    # High frequency movement in raw landmarks (normalized to torso scale to compare)
    stability_score = 1.0
    if len(valid_raw) > 2:
        # Calculate frame-to-frame velocity
        velocity = np.diff(valid_raw[:, :, :3], axis=0)
        acceleration = np.diff(velocity, axis=0)
        jitter = np.mean(np.linalg.norm(acceleration, axis=2))
        stability_score = max(0.0, 1.0 - (jitter * 5.0))  # Relaxed scale factor

    if stability_score < 0.1:
        reasons.append(f"Excessive landmark jitter detected (score {stability_score:.2f})")

    # 5. Smoothness (Post-normalization kinematics)
    # How smooth is the final normalized trajectory?
    smoothness_score = 1.0
    if len(normalized_landmarks) > 2:
        vel_norm = np.diff(normalized_landmarks[:, :, :3], axis=0)
        acc_norm = np.diff(vel_norm, axis=0)
        jerk = np.mean(np.linalg.norm(acc_norm, axis=2))
        smoothness_score = max(0.0, 1.0 - (jerk * 50.0))

    metrics = ValidationMetrics(
        detection_success_rate=success_rate,
        visibility_score=visibility_score,
        stability_score=stability_score,
        continuity_score=continuity_score,
        smoothness_score=smoothness_score,
    )

    is_valid = len(reasons) == 0

    if not is_valid:
        logger.warning(
            "dataset_validation_failed",
            reasons=reasons,
            metrics=vars(metrics),
        )
    else:
        logger.info("dataset_validation_passed", metrics=vars(metrics))

    return ValidationResult(is_valid=is_valid, metrics=metrics, failure_reasons=reasons)
