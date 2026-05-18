"""
============================================================
PhysioAI Pro V2 - Exercise Mistake Classifier
============================================================
PURPOSE
    Analyzes user motion data against the reference template
    to detect specific, actionable exercise mistakes rather
    than generic "incorrect form" messages.

    Each exercise has specific heuristics that check angles,
    trajectories, and symmetry.
============================================================
"""

from typing import List, Dict

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)


def classify_mistakes(
    exercise_id: str,
    user_angles: np.ndarray,
    user_angle_names: List[str],
    ref_ranges: Dict[str, dict],
    user_landmarks: np.ndarray = None,
) -> List[str]:
    """
    Detect exercise-specific mistakes based on user's performance.

    Args:
        exercise_id: The ID of the exercise (e.g. 't_fly')
        user_angles: (n_angles, n_frames) user angle curves
        user_angle_names: Names corresponding to the rows of user_angles
        ref_ranges: Reference angle ranges from the template
        user_landmarks: (Optional) raw/normalized user landmarks for trajectory checks
    """
    mistakes = []
    
    # Common ROM checks
    for i, name in enumerate(user_angle_names):
        if name in ref_ranges:
            user_min = np.min(user_angles[i])
            user_max = np.max(user_angles[i])
            user_range = user_max - user_min
            
            ref = ref_ranges[name]
            ref_range = ref["max"] - ref["min"]
            
            if ref_range > 15.0 and user_range < (ref_range * 0.6):
                # Only report once for general ROM.
                if "Complete the full range of motion." not in mistakes:
                    mistakes.append("Complete the full range of motion.")

    if exercise_id == "t_fly":
        mistakes.extend(_check_t_fly(user_angles, user_angle_names))
    elif exercise_id == "shoulder_release":
        mistakes.extend(_check_shoulder_release(user_angles, user_angle_names))
    elif exercise_id == "chin_tuck":
        mistakes.extend(_check_chin_tuck(user_angles, user_angle_names))

    return mistakes


def _get_angle_row(name: str, names: List[str], angles: np.ndarray) -> np.ndarray:
    try:
        idx = names.index(name)
        return angles[idx]
    except ValueError:
        return None


def _check_t_fly(angles: np.ndarray, names: List[str]) -> List[str]:
    mistakes = []
    
    # Check bent elbows
    elbow_l = _get_angle_row("elbow_left", names, angles)
    elbow_r = _get_angle_row("elbow_right", names, angles)
    
    if elbow_l is not None and elbow_r is not None:
        if np.mean(elbow_l) < 140 or np.mean(elbow_r) < 140:
            mistakes.append("Keep your arms straighter, don't bend elbows too much.")
            
    # Check asymmetry
    sh_l = _get_angle_row("shoulder_left", names, angles)
    sh_r = _get_angle_row("shoulder_right", names, angles)
    if sh_l is not None and sh_r is not None:
        diff = np.abs(sh_l - sh_r)
        if np.mean(diff) > 20:
            mistakes.append("Move both arms evenly. Your movement is asymmetric.")
            
    return mistakes


def _check_shoulder_release(angles: np.ndarray, names: List[str]) -> List[str]:
    mistakes = []
    
    arm_l = _get_angle_row("arm_raise_left", names, angles)
    arm_r = _get_angle_row("arm_raise_right", names, angles)
    
    if arm_l is not None and arm_r is not None:
        max_l = np.max(arm_l)
        max_r = np.max(arm_r)
        if max_l < 70 and max_r < 70:
            mistakes.append("Raise your arms higher to feel the stretch.")
        elif abs(max_l - max_r) > 25:
            mistakes.append("Uneven arm elevation. Try to raise both arms equally.")
            
    return mistakes


def _check_chin_tuck(angles: np.ndarray, names: List[str]) -> List[str]:
    mistakes = []
    
    neck_l = _get_angle_row("neck_left", names, angles)
    if neck_l is not None:
        if np.max(neck_l) - np.min(neck_l) < 10:
            mistakes.append("Insufficient neck retraction. Pull your chin further back.")
            
    return mistakes
