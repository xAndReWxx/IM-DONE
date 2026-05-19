"""
============================================================
PhysioAI Pro V2 - ROM Analyzer
============================================================
PURPOSE
    Analyzes Range of Motion (ROM) from a stream of joint angles,
    specifically focused on arm/elbow extension to identify
    potential mobility limitations.

    Outputs confidence scores and severity for restrictions.
============================================================
"""

from typing import Dict, List, Optional
import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)


def analyze_elbow_extension(
    elbow_angles_history: List[float],
    opposite_elbow_angles_history: List[float],
    fps: float = 15.0
) -> Optional[Dict]:
    """
    Detect if the elbow is persistently bent over a window of time,
    comparing it to the opposite arm to identify asymmetric mobility limits.

    Args:
        elbow_angles_history: Recent angles of the target elbow.
        opposite_elbow_angles_history: Recent angles of the opposite elbow.
        fps: The approximate framerate.

    Returns:
        Dict with limitation metadata if detected, else None.
    """
    # Need at least 3 seconds of data to make a confident assessment
    min_frames = int(fps * 3.0)
    
    if len(elbow_angles_history) < min_frames or len(opposite_elbow_angles_history) < min_frames:
        return None

    recent_target = np.array(elbow_angles_history[-min_frames:])
    recent_opposite = np.array(opposite_elbow_angles_history[-min_frames:])

    # Maximum extension achieved in this window (180 is fully straight)
    max_extension_target = np.max(recent_target)
    max_extension_opposite = np.max(recent_opposite)
    
    # Average extension in this window
    avg_extension_target = np.mean(recent_target)
    avg_extension_opposite = np.mean(recent_opposite)

    # Variance (is the arm moving or frozen?)
    var_target = np.var(recent_target)

    # RULE 1: The arm remains bent (never reaches full extension)
    # AND it is persistently bent (average is low)
    # AND the opposite arm is significantly straighter
    if max_extension_target < 145.0 and var_target < 50.0:
        asymmetry = max_extension_opposite - max_extension_target
        
        if asymmetry > 15.0:
            # We have a confident limitation
            severity = "mild"
            if max_extension_target < 110.0:
                severity = "severe"
            elif max_extension_target < 130.0:
                severity = "moderate"
                
            confidence = min(100, int(50 + (asymmetry * 1.5)))
            
            return {
                "issue": "restricted_arm_mobility",
                "severity": severity,
                "confidence": confidence,
                "max_extension": float(max_extension_target),
                "asymmetry_deg": float(asymmetry)
            }
            
    return None
