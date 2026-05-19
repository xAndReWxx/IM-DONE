"""
============================================================
PhysioAI Pro V2 - Asymmetry Detector
============================================================
PURPOSE
    Detects persistent asymmetries between left and right
    body sides during posture scanning.
============================================================
"""

from typing import List, Dict, Optional
import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)


def detect_shoulder_asymmetry(
    shoulder_l_history: List[float],
    shoulder_r_history: List[float],
    fps: float = 15.0
) -> Optional[Dict]:
    """
    Detect if one shoulder is persistently higher than the other.
    (Requires vertical elevation signals for left and right shoulders).
    """
    min_frames = int(fps * 2.0)
    if len(shoulder_l_history) < min_frames or len(shoulder_r_history) < min_frames:
        return None
        
    recent_l = np.array(shoulder_l_history[-min_frames:])
    recent_r = np.array(shoulder_r_history[-min_frames:])
    
    avg_l = np.mean(recent_l)
    avg_r = np.mean(recent_r)
    
    diff = abs(avg_l - avg_r)
    if diff > 0.05:  # 5% of screen height
        side = "left" if avg_l < avg_r else "right" # Assuming lower y is higher on screen
        return {
            "issue": "uneven_shoulders",
            "higher_side": side,
            "confidence": min(100, int(50 + diff * 500))
        }
        
    return None
