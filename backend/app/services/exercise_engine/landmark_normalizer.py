"""
============================================================
PhysioAI Pro V2 - Landmark Normalizer
============================================================
PURPOSE
    Normalizes raw MediaPipe landmarks to remove camera-,
    position-, and body-size-dependent variation so exercise
    motion can be compared across different users.

NORMALIZATION STEPS
    1. Interpolate missing frames (failed MediaPipe detections)
    2. Filter low-visibility landmarks
    3. Center on hip midpoint (translation invariance)
    4. Scale by torso length (scale invariance)
    5. Apply temporal smoothing (EMA filter to reduce jitter)

POST-NORMALIZATION
    Landmarks are comparable regardless of:
      - camera distance
      - body size / height
      - position in frame
      - screen resolution
============================================================
"""

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Anchor landmark indices.
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24

# Minimum visibility to consider a landmark valid.
MIN_VISIBILITY = 0.3

# EMA alpha for temporal smoothing (lower = smoother).
SMOOTHING_ALPHA = 0.6


def interpolate_missing_frames(
    landmarks: np.ndarray,
    valid_mask: np.ndarray,
) -> np.ndarray:
    """
    Interpolate landmark values for frames where detection failed.

    For each landmark coordinate, uses linear interpolation between
    the nearest valid frames. Leading/trailing gaps are filled with
    the nearest valid value.

    Args:
        landmarks: (N, 33, 4) raw landmarks.
        valid_mask: (N,) boolean — True where detection succeeded.

    Returns:
        (N, 33, 4) with interpolated values.
    """
    result = landmarks.copy()
    n_frames = len(landmarks)
    valid_indices = np.where(valid_mask)[0]

    if len(valid_indices) == 0 or len(valid_indices) == n_frames:
        return result

    invalid_indices = np.where(~valid_mask)[0]
    interpolated_count = 0

    # Interpolate each landmark coordinate independently.
    for lm_idx in range(33):
        for coord in range(4):  # x, y, z, visibility
            values = landmarks[:, lm_idx, coord]
            valid_values = values[valid_mask]

            if len(valid_values) == 0:
                continue

            # Interpolate.
            interpolated = np.interp(
                np.arange(n_frames),
                valid_indices,
                valid_values,
            )
            result[:, lm_idx, coord] = interpolated

    interpolated_count = len(invalid_indices)
    if interpolated_count > 0:
        logger.info(
            "frames_interpolated",
            count=interpolated_count,
            total=n_frames,
            pct=f"{interpolated_count / n_frames * 100:.1f}%",
        )

    return result


def filter_low_visibility(
    landmarks: np.ndarray,
    threshold: float = MIN_VISIBILITY,
) -> np.ndarray:
    """
    Zero out landmarks with visibility below threshold.
    This prevents unreliable detections from corrupting angles.
    """
    result = landmarks.copy()
    low_vis = result[:, :, 3] < threshold
    result[low_vis, :3] = 0.0
    return result


def center_and_scale(landmarks: np.ndarray) -> np.ndarray:
    """
    Normalize each frame:
      1. Center on hip midpoint (x, y)
      2. Scale so average torso length = 1.0

    This makes the data translation- and scale-invariant.
    """
    result = landmarks.copy()
    n_frames = result.shape[0]

    for i in range(n_frames):
        lm = result[i]

        # Skip all-zero frames (shouldn't exist after interpolation,
        # but be defensive).
        if np.allclose(lm[:, :2], 0.0):
            continue

        # Hip midpoint for centering.
        hip_mid = (lm[LM_LEFT_HIP, :2] + lm[LM_RIGHT_HIP, :2]) / 2.0
        lm[:, 0] -= hip_mid[0]
        lm[:, 1] -= hip_mid[1]

        # Torso length: shoulder midpoint → hip midpoint.
        sh_mid = (lm[LM_LEFT_SHOULDER, :2] + lm[LM_RIGHT_SHOULDER, :2]) / 2.0
        # hip_mid is now (0, 0) after centering
        torso_len = np.linalg.norm(sh_mid)
        if torso_len < 1e-6:
            torso_len = 1.0  # prevent division by zero

        lm[:, :3] /= torso_len
        result[i] = lm

    return result


def temporal_smooth(
    landmarks: np.ndarray,
    alpha: float = SMOOTHING_ALPHA,
) -> np.ndarray:
    """
    Apply Exponential Moving Average smoothing to reduce jitter.

    Only smooths x, y, z — visibility is left unchanged.
    Alpha controls responsiveness: 1.0 = no smoothing, 0.0 = infinite lag.
    """
    result = landmarks.copy()
    n_frames = result.shape[0]

    if n_frames < 2:
        return result

    for i in range(1, n_frames):
        result[i, :, :3] = alpha * result[i, :, :3] + (1 - alpha) * result[i - 1, :, :3]

    return result


def normalize_landmarks(
    raw_landmarks: np.ndarray,
    valid_mask: np.ndarray,
    smooth: bool = True,
    smooth_alpha: float = SMOOTHING_ALPHA,
) -> np.ndarray:
    """
    Full normalization pipeline:
      1. Interpolate missing frames
      2. Filter low-visibility landmarks
      3. Center on hip midpoint + scale by torso
      4. (Optional) Temporal smoothing

    Args:
        raw_landmarks: (N, 33, 4) from video processor.
        valid_mask: (N,) boolean.
        smooth: Whether to apply EMA smoothing.
        smooth_alpha: EMA coefficient.

    Returns:
        (N, 33, 4) normalized landmarks.
    """
    # Step 1: Interpolate gaps.
    data = interpolate_missing_frames(raw_landmarks, valid_mask)

    # Step 2: Filter unreliable landmarks.
    data = filter_low_visibility(data)

    # Step 3: Center and scale.
    data = center_and_scale(data)

    # Step 4: Temporal smoothing.
    if smooth:
        data = temporal_smooth(data, alpha=smooth_alpha)

    logger.info("landmarks_normalized", frames=data.shape[0])
    return data
