"""
============================================================
PhysioAI Pro V2 - Angle Extractor
============================================================
PURPOSE
    Computes joint angle timelines from normalized landmarks.
    Every important biomechanical angle is tracked per-frame
    to build a complete motion profile.

ANGLES TRACKED
    - neck:         ear → shoulder → hip
    - left_shoulder: elbow → shoulder → hip
    - right_shoulder: elbow → shoulder → hip
    - left_elbow:   wrist → elbow → shoulder
    - right_elbow:  wrist → elbow → shoulder
    - spine_lean:   shoulder_mid → hip_mid vs vertical
    - left_hip:     shoulder → hip → knee
    - right_hip:    shoulder → hip → knee
    - left_knee:    hip → knee → ankle
    - right_knee:   hip → knee → ankle
    - shoulder_tilt: horizontal angle between shoulders

OUTPUT
    Dictionary of angle name → numpy array of per-frame values.
============================================================
"""

from typing import Dict, List, Tuple

import numpy as np

from app.services.ai.geometry import (
    calculate_angle,
    vertical_angle,
    horizontal_tilt,
    midpoint,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# MediaPipe landmark indices.
LM_LEFT_EAR = 7
LM_RIGHT_EAR = 8
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_ELBOW = 13
LM_RIGHT_ELBOW = 14
LM_LEFT_WRIST = 15
LM_RIGHT_WRIST = 16
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24
LM_LEFT_KNEE = 25
LM_RIGHT_KNEE = 26
LM_LEFT_ANKLE = 27
LM_RIGHT_ANKLE = 28

# Angle definitions: (name, landmark_a, landmark_b_vertex, landmark_c)
# For 3-point angles using calculate_angle.
THREE_POINT_ANGLES: List[Tuple[str, int, int, int]] = [
    ("neck_left",       LM_LEFT_EAR,      LM_LEFT_SHOULDER,  LM_LEFT_HIP),
    ("neck_right",      LM_RIGHT_EAR,     LM_RIGHT_SHOULDER, LM_RIGHT_HIP),
    ("shoulder_left",   LM_LEFT_ELBOW,    LM_LEFT_SHOULDER,  LM_LEFT_HIP),
    ("shoulder_right",  LM_RIGHT_ELBOW,   LM_RIGHT_SHOULDER, LM_RIGHT_HIP),
    ("elbow_left",      LM_LEFT_WRIST,    LM_LEFT_ELBOW,     LM_LEFT_SHOULDER),
    ("elbow_right",     LM_RIGHT_WRIST,   LM_RIGHT_ELBOW,    LM_RIGHT_SHOULDER),
    ("hip_left",        LM_LEFT_SHOULDER,  LM_LEFT_HIP,       LM_LEFT_KNEE),
    ("hip_right",       LM_RIGHT_SHOULDER, LM_RIGHT_HIP,      LM_RIGHT_KNEE),
    ("knee_left",       LM_LEFT_HIP,       LM_LEFT_KNEE,      LM_LEFT_ANKLE),
    ("knee_right",      LM_RIGHT_HIP,      LM_RIGHT_KNEE,     LM_RIGHT_ANKLE),
    # Arm raise angles (wrist relative to shoulder/hip).
    ("arm_raise_left",  LM_LEFT_WRIST,    LM_LEFT_SHOULDER,  LM_LEFT_HIP),
    ("arm_raise_right", LM_RIGHT_WRIST,   LM_RIGHT_SHOULDER, LM_RIGHT_HIP),
]


def extract_angles(landmarks: np.ndarray) -> Dict[str, np.ndarray]:
    """
    Compute all tracked angles for every frame.

    Args:
        landmarks: (N, 33, 4) normalized landmarks.

    Returns:
        Dict of angle_name → (N,) numpy array of degrees.
    """
    n_frames = landmarks.shape[0]
    angles: Dict[str, np.ndarray] = {}

    # ── Three-point joint angles ──
    for name, a_idx, b_idx, c_idx in THREE_POINT_ANGLES:
        values = np.zeros(n_frames, dtype=np.float64)
        for i in range(n_frames):
            lm = landmarks[i]
            # Skip zero-frames.
            if np.allclose(lm[b_idx, :2], 0.0):
                values[i] = np.nan
                continue
            values[i] = calculate_angle(
                lm[a_idx, :2], lm[b_idx, :2], lm[c_idx, :2]
            )
        # Interpolate NaN gaps.
        values = _interpolate_nans(values)
        angles[name] = values

    # ── Spine lean (vertical angle: shoulder_mid → hip_mid) ──
    spine_lean = np.zeros(n_frames, dtype=np.float64)
    for i in range(n_frames):
        lm = landmarks[i]
        sh_mid = midpoint(lm[LM_LEFT_SHOULDER, :2], lm[LM_RIGHT_SHOULDER, :2])
        hp_mid = midpoint(lm[LM_LEFT_HIP, :2], lm[LM_RIGHT_HIP, :2])
        spine_lean[i] = vertical_angle(sh_mid, hp_mid)
    angles["spine_lean"] = _interpolate_nans(spine_lean)

    # ── Shoulder tilt (horizontal level) ──
    sh_tilt = np.zeros(n_frames, dtype=np.float64)
    for i in range(n_frames):
        lm = landmarks[i]
        sh_tilt[i] = horizontal_tilt(
            lm[LM_LEFT_SHOULDER, :2], lm[LM_RIGHT_SHOULDER, :2]
        )
    angles["shoulder_tilt"] = _interpolate_nans(sh_tilt)

    # ── Forward head angle (avg of ear-shoulder vertical) ──
    fh = np.zeros(n_frames, dtype=np.float64)
    for i in range(n_frames):
        lm = landmarks[i]
        left = vertical_angle(lm[LM_LEFT_EAR, :2], lm[LM_LEFT_SHOULDER, :2])
        right = vertical_angle(lm[LM_RIGHT_EAR, :2], lm[LM_RIGHT_SHOULDER, :2])
        fh[i] = (left + right) / 2.0
    angles["forward_head"] = _interpolate_nans(fh)

    logger.info("angles_extracted", n_angles=len(angles), n_frames=n_frames)
    return angles


def _interpolate_nans(values: np.ndarray) -> np.ndarray:
    """Linearly interpolate NaN values in a 1D array."""
    nans = np.isnan(values)
    if not nans.any():
        return values
    if nans.all():
        return np.zeros_like(values)
    result = values.copy()
    result[nans] = np.interp(
        np.where(nans)[0],
        np.where(~nans)[0],
        values[~nans],
    )
    return result


def get_primary_angle_names() -> List[str]:
    """Return names of the most important angles for display/comparison."""
    return [
        "neck_left", "neck_right",
        "shoulder_left", "shoulder_right",
        "elbow_left", "elbow_right",
        "hip_left", "hip_right",
        "spine_lean", "shoulder_tilt", "forward_head",
        "arm_raise_left", "arm_raise_right",
    ]
