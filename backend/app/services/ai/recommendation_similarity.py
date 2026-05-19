import numpy as np
from typing import List, Dict, Any, Optional
from app.models.packets import ExerciseCard
from app.services.ai.exercise_catalog import EXERCISES
from app.services.ai.geometry import vertical_angle, horizontal_tilt, midpoint

def normalize_landmarks(landmarks: np.ndarray) -> np.ndarray:
    """Center and scale landmarks."""
    # Center around mid-hip
    hip_l = landmarks[23][:2]
    hip_r = landmarks[24][:2]
    mid_hip = (hip_l + hip_r) / 2.0
    
    norm = landmarks.copy()
    norm[:, 0] -= mid_hip[0]
    norm[:, 1] -= mid_hip[1]
    
    # Scale based on torso length (mid-shoulder to mid-hip)
    sh_l = landmarks[11][:2]
    sh_r = landmarks[12][:2]
    mid_sh = (sh_l + sh_r) / 2.0
    torso_len = np.linalg.norm(mid_sh - mid_hip)
    
    if torso_len > 0:
        norm[:, :2] /= torso_len
        
    return norm

def extract_posture_signature(landmarks: np.ndarray) -> Dict[str, float]:
    """Extract key normalized angle metrics to form a posture signature."""
    # 2D points
    ear_l = landmarks[7][:2]
    ear_r = landmarks[8][:2]
    sh_l = landmarks[11][:2]
    sh_r = landmarks[12][:2]
    hip_l = landmarks[23][:2]
    hip_r = landmarks[24][:2]
    elbow_l = landmarks[13][:2]
    elbow_r = landmarks[14][:2]
    wrist_l = landmarks[15][:2]
    wrist_r = landmarks[16][:2]

    # Angles
    fh_l = vertical_angle(ear_l, sh_l)
    fh_r = vertical_angle(ear_r, sh_r)
    fh_avg = (fh_l + fh_r) / 2.0
    
    tilt = horizontal_tilt(sh_l, sh_r)
    lean = vertical_angle(midpoint(sh_l, sh_r), midpoint(hip_l, hip_r))
    
    # Arm extension (angle between shoulder, elbow, wrist)
    # Using simple cosine rule or dot product for internal angle
    def inner_angle(a, b, c):
        ba = a - b
        bc = c - b
        cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
        return np.degrees(np.arccos(np.clip(cosine_angle, -1.0, 1.0)))

    elbow_angle_l = inner_angle(sh_l, elbow_l, wrist_l)
    elbow_angle_r = inner_angle(sh_r, elbow_r, wrist_r)
    
    return {
        "forward_head": fh_avg,
        "shoulder_tilt": tilt,
        "spine_lean": lean,
        "elbow_ext_l": elbow_angle_l,
        "elbow_ext_r": elbow_angle_r,
        "arm_asymmetry": abs(elbow_angle_l - elbow_angle_r)
    }

def get_similarity_recommendations(landmarks: Optional[np.ndarray], limit: int = 3) -> List[ExerciseCard]:
    """
    Compare posture signature against known limitation profiles to rank exercises.
    Returns ranked ExerciseCards based on similarity/confidence.
    """
    if landmarks is None or len(landmarks) < 33:
        return []

    norm_lm = normalize_landmarks(landmarks)
    sig = extract_posture_signature(norm_lm)
    
    # Confidence scoring per target profile
    scores: Dict[str, float] = {}

    # Profile: Forward Head -> shoulder_release
    # Forward head signature: high fh_avg
    fh_confidence = np.clip((sig["forward_head"] - 15) / 25.0, 0, 1.0)
    scores["shoulder_release"] = float(fh_confidence)

    # Profile: Rounded Shoulders / Asymmetry -> shoulder_release, t_fly
    # Signature: high shoulder tilt or spine lean
    shoulder_confidence = np.clip((sig["shoulder_tilt"] - 5) / 15.0, 0, 1.0)
    lean_confidence = np.clip((sig["spine_lean"] - 5) / 15.0, 0, 1.0)
    upper_body_issue = max(shoulder_confidence, lean_confidence)
    # Since shoulder_release is also for forward head, combine the confidence
    scores["shoulder_release"] = max(scores.get("shoulder_release", 0.0), float(upper_body_issue * 0.9))
    scores["t_fly"] = float(upper_body_issue)

    # Profile: Restricted Arm Mobility -> elbow
    # Signature: high arm asymmetry or low absolute extension (< 150 deg)
    ext_limitation_l = np.clip((160 - sig["elbow_ext_l"]) / 60.0, 0, 1.0)
    ext_limitation_r = np.clip((160 - sig["elbow_ext_r"]) / 60.0, 0, 1.0)
    asymmetry_conf = np.clip(sig["arm_asymmetry"] / 30.0, 0, 1.0)
    
    arm_confidence = max(ext_limitation_l, ext_limitation_r, asymmetry_conf)
    scores["elbow"] = float(arm_confidence)

    # Filter out low confidence and sort
    ranked = sorted(
        [(ex_id, conf) for ex_id, conf in scores.items() if conf > 0.3],
        key=lambda x: x[1],
        reverse=True
    )

    out = []
    for ex_id, conf in ranked:
        if ex_id in EXERCISES:
            card = EXERCISES[ex_id]
            out.append(card)
            if len(out) >= limit:
                break
                
    return out
