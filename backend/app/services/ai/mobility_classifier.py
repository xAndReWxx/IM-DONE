"""
============================================================
PhysioAI Pro V2 - Mobility Classifier
============================================================
PURPOSE
    Orchestrates the ROM Analyzer and Asymmetry Detector to 
    identify specific mobility limitations during posture scanning.
    Maintains history windows for relevant joint angles.
============================================================
"""

from typing import Dict, List, Optional
from collections import deque
import numpy as np

from app.services.ai.geometry import calculate_angle
from app.services.ai.rom_analyzer import analyze_elbow_extension
from app.services.ai.asymmetry_detector import detect_shoulder_asymmetry
from app.utils.logger import get_logger

logger = get_logger(__name__)

# MediaPipe landmark indices
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_ELBOW = 13
LM_RIGHT_ELBOW = 14
LM_LEFT_WRIST = 15
LM_RIGHT_WRIST = 16

class MobilityClassifier:
    """
    Analyzes streams of landmarks to detect persistent mobility issues.
    Maintains a rolling window of angles.
    """
    def __init__(self, fps: float = 15.0):
        self.fps = fps
        self.history_frames = int(fps * 5.0) # 5 seconds of history
        
        self.left_elbow_angles: deque = deque(maxlen=self.history_frames)
        self.right_elbow_angles: deque = deque(maxlen=self.history_frames)
        
        self.left_shoulder_y: deque = deque(maxlen=self.history_frames)
        self.right_shoulder_y: deque = deque(maxlen=self.history_frames)
        
    def process_frame(self, landmarks: np.ndarray) -> List[Dict]:
        """
        Process a single frame's landmarks and return detected mobility issues.
        """
        issues = []
        
        # Calculate angles
        left_elbow = calculate_angle(
            landmarks[LM_LEFT_SHOULDER, :2],
            landmarks[LM_LEFT_ELBOW, :2],
            landmarks[LM_LEFT_WRIST, :2]
        )
        right_elbow = calculate_angle(
            landmarks[LM_RIGHT_SHOULDER, :2],
            landmarks[LM_RIGHT_ELBOW, :2],
            landmarks[LM_RIGHT_WRIST, :2]
        )
        
        self.left_elbow_angles.append(left_elbow)
        self.right_elbow_angles.append(right_elbow)
        self.left_shoulder_y.append(landmarks[LM_LEFT_SHOULDER, 1])
        self.right_shoulder_y.append(landmarks[LM_RIGHT_SHOULDER, 1])
        
        # 1. Analyze Arm Extension
        left_arm_issue = analyze_elbow_extension(
            list(self.left_elbow_angles), 
            list(self.right_elbow_angles), 
            self.fps
        )
        if left_arm_issue:
            left_arm_issue["side"] = "left"
            issues.append(left_arm_issue)
            
        right_arm_issue = analyze_elbow_extension(
            list(self.right_elbow_angles), 
            list(self.left_elbow_angles), 
            self.fps
        )
        if right_arm_issue:
            right_arm_issue["side"] = "right"
            issues.append(right_arm_issue)
            
        # 2. Analyze Shoulder Asymmetry
        shoulder_issue = detect_shoulder_asymmetry(
            list(self.left_shoulder_y),
            list(self.right_shoulder_y),
            self.fps
        )
        if shoulder_issue:
            issues.append(shoulder_issue)
            
        return issues
