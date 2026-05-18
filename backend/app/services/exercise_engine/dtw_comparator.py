"""
============================================================
PhysioAI Pro V2 - DTW Comparator
============================================================
PURPOSE
    Dynamic Time Warping (DTW) implementation for comparing
    user motion sequences against reference templates.

    DTW handles temporal misalignment — the user may move
    faster or slower than the reference, and DTW finds the
    optimal alignment between the two sequences.

IMPLEMENTATION
    Pure NumPy DTW (no external dependency). Optimized with
    a Sakoe-Chiba band constraint to limit warping and keep
    O(N·W) complexity where W is the band width.

PUBLIC API
    dtw_distance(seq_a, seq_b) → float
    dtw_similarity(seq_a, seq_b) → float [0–1]
    compare_to_template(user_angles, template) → ComparisonResult
============================================================
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from app.services.exercise_engine.mistake_classifier import classify_mistakes
from app.utils.logger import get_logger

logger = get_logger(__name__)


def dtw_distance(
    seq_a: np.ndarray,
    seq_b: np.ndarray,
    band_ratio: float = 0.2,
) -> float:
    """
    Compute DTW distance between two 1D sequences.

    Uses a Sakoe-Chiba band for efficiency.
    Returns the normalized DTW distance (lower = more similar).
    """
    n = len(seq_a)
    m = len(seq_b)

    if n == 0 or m == 0:
        return float("inf")

    band = max(3, int(max(n, m) * band_ratio))

    # Cost matrix with infinity padding.
    dtw_matrix = np.full((n + 1, m + 1), np.inf, dtype=np.float64)
    dtw_matrix[0, 0] = 0.0

    for i in range(1, n + 1):
        j_start = max(1, i - band)
        j_end = min(m, i + band) + 1
        for j in range(j_start, j_end):
            cost = (seq_a[i - 1] - seq_b[j - 1]) ** 2
            dtw_matrix[i, j] = cost + min(
                dtw_matrix[i - 1, j],       # insertion
                dtw_matrix[i, j - 1],        # deletion
                dtw_matrix[i - 1, j - 1],    # match
            )

    # Normalized by path length.
    total = dtw_matrix[n, m]
    return float(np.sqrt(total / (n + m)))


def dtw_similarity(
    seq_a: np.ndarray,
    seq_b: np.ndarray,
    max_distance: float = 30.0,
) -> float:
    """
    Compute similarity score [0, 1] between two sequences.
    1.0 = identical, 0.0 = maximally different.
    """
    dist = dtw_distance(seq_a, seq_b)
    # Sigmoid-like mapping: distance → similarity.
    return float(max(0.0, 1.0 - (dist / max_distance)))


def multi_angle_dtw_similarity(
    user_angles: np.ndarray,
    ref_angles: np.ndarray,
    max_distance: float = 30.0,
) -> tuple[float, List[float]]:
    """
    Compare multiple angle curves between user and reference.

    Args:
        user_angles: (n_angles, user_steps)
        ref_angles: (n_angles, ref_steps)
        max_distance: normalization constant

    Returns:
        (overall_similarity, per_angle_similarities)
    """
    n_angles = min(user_angles.shape[0], ref_angles.shape[0])
    per_angle = []

    for i in range(n_angles):
        sim = dtw_similarity(user_angles[i], ref_angles[i], max_distance)
        per_angle.append(sim)

    overall = float(np.mean(per_angle)) if per_angle else 0.0
    return overall, per_angle


def trajectory_similarity(
    user_landmarks: np.ndarray,
    ref_landmarks: np.ndarray,
    max_distance: float = 0.5,
) -> float:
    """
    Compare normalized landmark trajectories using DTW.
    user_landmarks: (33, 4, CANONICAL_STEPS)
    """
    # Average across all 33 landmarks for spatial difference.
    # We compare the (x,y) coordinates.
    n_lms = min(user_landmarks.shape[0], ref_landmarks.shape[0])
    similarities = []
    
    for i in range(n_lms):
        # Flatten x,y for this landmark into a single sequence for simple comparison
        # Or compute distance between (x,y) pairs. We'll use distance.
        u_xy = user_landmarks[i, :2, :] # (2, steps)
        r_xy = ref_landmarks[i, :2, :]
        
        # Calculate point-wise distances if aligned
        dist = np.mean(np.linalg.norm(u_xy - r_xy, axis=0))
        sim = max(0.0, 1.0 - (dist / max_distance))
        similarities.append(sim)
        
    return float(np.mean(similarities)) if similarities else 0.0


@dataclass
class ComparisonResult:
    """Result of comparing user motion to a reference template."""
    overall_similarity: float       # 0–1
    trajectory_similarity: float    # 0-1
    per_angle_similarity: List[float]
    quality_score: int              # 0–100
    phase_accuracy: float           # 0–1
    timing_score: float             # 0–1
    range_score: float              # 0–1
    smoothness_score: float         # 0-1
    corrections: List[str]          # suggested corrections


def compare_to_template(
    exercise_id: str,
    user_angle_curves: np.ndarray,
    template_canonical: np.ndarray,
    template_angle_ranges: dict,
    template_angle_names: List[str],
    user_landmarks: Optional[np.ndarray] = None,
    template_landmarks: Optional[np.ndarray] = None,
    user_fps: float = 15.0,
    template_fps: float = 30.0,
) -> ComparisonResult:
    """
    Full comparison of user's current rep against a reference template.

    Args:
        exercise_id: The ID of the exercise.
        user_angle_curves: (n_angles, user_steps) — current user motion
        template_canonical: (n_angles, 100) — reference canonical rep
        template_angle_ranges: {angle_name: (min, max)} from template
        template_angle_names: list of angle names
        user_landmarks: (Optional) (33, 4, 100) user landmark trajectories
        template_landmarks: (Optional) (33, 4, 100) template landmark trajectories
        user_fps: user's frame rate
        template_fps: template's source FPS

    Returns:
        ComparisonResult with scores and corrections.
    """
    corrections: List[str] = []

    # ── 1. DTW Similarity ──
    overall_sim, per_angle_sims = multi_angle_dtw_similarity(
        user_angle_curves, template_canonical
    )

    # ── 2. Range Score ──
    # Check if user reaches the full range of motion.
    range_scores = []
    for i, name in enumerate(template_angle_names):
        if i >= user_angle_curves.shape[0]:
            break
        user_min = float(np.min(user_angle_curves[i]))
        user_max = float(np.max(user_angle_curves[i]))
        user_range = user_max - user_min

        ref_range_pair = template_angle_ranges.get(name)
        if ref_range_pair:
            ref_range = ref_range_pair[1] - ref_range_pair[0]
            if ref_range > 0:
                ratio = min(1.0, user_range / ref_range)
                range_scores.append(ratio)
                if ratio < 0.6:
                    corrections.append("Complete the full range of motion.")
            else:
                range_scores.append(1.0)

    range_score = float(np.mean(range_scores)) if range_scores else 0.5

    # ── 3. Trajectory Score ──
    traj_sim = 0.5
    if user_landmarks is not None and template_landmarks is not None:
        traj_sim = trajectory_similarity(user_landmarks, template_landmarks)
        
    # ── 4. Timing Score ──
    # Compare rep duration ratio.
    if user_angle_curves.shape[1] > 5:
        user_steps = user_angle_curves.shape[1]
        ref_steps = template_canonical.shape[1]
        duration_ratio = user_steps / max(1, ref_steps)
        # Ideal ratio ≈ 1.0 (adjusted for FPS difference).
        fps_adjusted = duration_ratio * (template_fps / max(1.0, user_fps))
        timing_score = max(0.0, 1.0 - abs(1.0 - fps_adjusted) * 0.5)
        if fps_adjusted < 0.5:
            corrections.append("Slow down — take your time with the movement.")
        elif fps_adjusted > 2.0:
            corrections.append("Move a bit faster to match the exercise tempo.")
    else:
        timing_score = 0.5

    # ── 5. Smoothness & Phase Accuracy ──
    smoothness_scores = []
    for i in range(user_angle_curves.shape[0]):
        curve = user_angle_curves[i]
        if len(curve) > 2:
            # Second derivative (jerk) — lower = smoother.
            jerk = np.diff(curve, n=2)
            jerk_rms = float(np.sqrt(np.mean(jerk ** 2)))
            # Normalize: good form ≈ jerk < 5.
            smoothness = max(0.0, 1.0 - jerk_rms / 15.0)
            smoothness_scores.append(smoothness)
            
    smoothness_score = float(np.mean(smoothness_scores)) if smoothness_scores else 0.5
    phase_accuracy = max(0.0, overall_sim * 0.5 + smoothness_score * 0.5)

    if smoothness_score < 0.5:
        corrections.append("Try to move more smoothly — avoid jerky movements.")

    # ── 6. Exercise Mistake Classification ──
    specific_mistakes = classify_mistakes(
        exercise_id, 
        user_angle_curves, 
        template_angle_names, 
        template_angle_ranges
    )
    for m in specific_mistakes:
        if m not in corrections:
            corrections.append(m)

    # ── 7. Quality Score (0–100) Weighted Multi-Signal ──
    # 0.4 * angle + 0.3 * trajectory + 0.2 * timing + 0.1 * smoothness
    quality_score = int(round(
        overall_sim * 40 +
        traj_sim * 30 +
        timing_score * 20 +
        smoothness_score * 10
    ))
    quality_score = max(0, min(100, quality_score))

    # ── 8. Similarity-based corrections (if no specific mistakes found) ──
    if not specific_mistakes:
        if overall_sim < 0.4:
            corrections.append("Your form needs improvement — watch the reference video.")
        elif overall_sim < 0.6:
            corrections.append("Getting closer — focus on matching the exercise motion.")
        elif overall_sim > 0.85:
            corrections.append("Excellent form!")

    return ComparisonResult(
        overall_similarity=round(overall_sim, 3),
        trajectory_similarity=round(traj_sim, 3),
        per_angle_similarity=[round(s, 3) for s in per_angle_sims],
        quality_score=quality_score,
        phase_accuracy=round(phase_accuracy, 3),
        timing_score=round(timing_score, 3),
        range_score=round(range_score, 3),
        smoothness_score=round(smoothness_score, 3),
        corrections=corrections[:3],  # Limit to top 3.
    )
