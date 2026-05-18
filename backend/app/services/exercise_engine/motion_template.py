"""
============================================================
PhysioAI Pro V2 - Motion Template Generator
============================================================
PURPOSE
    Converts raw landmark datasets + detected phases into a
    reusable MotionTemplate — the "ideal" reference for each
    exercise.

TEMPLATE STRUCTURE
    A MotionTemplate contains:
      - angle_curves: per-angle time series for one canonical rep
      - phase_boundaries: normalized [0,1] phase start/end times
      - landmark_trajectory: averaged normalized landmark path
      - rep_duration_frames: average rep length in frames
      - angle_ranges: min/max for each tracked angle
      - movement_signature: compact feature vector for quick matching

CANONICAL REP EXTRACTION
    1. Detect all reps in the video using PhaseDetector.
    2. Extract each rep's angle curves.
    3. Resample each rep to a fixed length (100 steps).
    4. Average across all reps → canonical rep.
============================================================
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import json

import numpy as np

from app.services.ai.geometry import calculate_angle
from app.services.exercise_engine.phase_detector import (
    detect_phases,
    PhaseSequence,
    PhaseLabel,
    EXERCISE_ANGLES,
    DEFAULT_ANGLES,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Fixed number of steps for canonical rep resampling.
CANONICAL_REP_STEPS = 100


@dataclass
class MotionTemplate:
    """The reference motion model for one exercise."""
    exercise_id: str
    # (n_angles, CANONICAL_REP_STEPS) — averaged angle curves for one ideal rep.
    canonical_angles: np.ndarray
    # (33, 4, CANONICAL_REP_STEPS) - averaged landmark trajectories.
    canonical_landmarks: np.ndarray
    # Per-angle (min, max) ranges observed in reference data.
    angle_ranges: Dict[str, tuple[float, float]] = field(default_factory=dict)
    # Normalized phase boundaries: list of (start_pct, end_pct, label).
    phase_boundaries: List[tuple[float, float, str]] = field(default_factory=list)
    # Average rep duration in frames (at source FPS).
    rep_duration_frames: float = 0.0
    # Source FPS of the reference video.
    source_fps: float = 30.0
    # Angle definition keys.
    angle_names: List[str] = field(default_factory=list)
    # Compact signature (for fast similarity check).
    movement_signature: Optional[np.ndarray] = None

    def save(self, path: Path) -> None:
        """Save template to disk (.npz + .json metadata)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        npz_path = path.with_suffix(".npz")
        np.savez_compressed(
            npz_path,
            canonical_angles=self.canonical_angles,
            canonical_landmarks=self.canonical_landmarks,
            movement_signature=self.movement_signature if self.movement_signature is not None else np.array([]),
        )
        meta = {
            "exercise_id": self.exercise_id,
            "angle_ranges": self.angle_ranges,
            "phase_boundaries": self.phase_boundaries,
            "rep_duration_frames": self.rep_duration_frames,
            "source_fps": self.source_fps,
            "angle_names": self.angle_names,
            "canonical_steps": CANONICAL_REP_STEPS,
        }
        json_path = path.with_suffix(".json")
        json_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        logger.info("template_saved", exercise=self.exercise_id, path=str(npz_path))

    @classmethod
    def load(cls, path: Path) -> Optional["MotionTemplate"]:
        """Load a template from disk."""
        npz_path = path.with_suffix(".npz")
        json_path = path.with_suffix(".json")
        if not npz_path.exists() or not json_path.exists():
            return None
        try:
            data = np.load(npz_path)
            meta = json.loads(json_path.read_text(encoding="utf-8"))
            sig = data.get("movement_signature")
            if sig is not None and sig.size == 0:
                sig = None
            return cls(
                exercise_id=meta["exercise_id"],
                canonical_angles=data["canonical_angles"],
                canonical_landmarks=data.get("canonical_landmarks", np.zeros((33, 4, CANONICAL_REP_STEPS))),
                angle_ranges=meta.get("angle_ranges", {}),
                phase_boundaries=meta.get("phase_boundaries", []),
                rep_duration_frames=meta.get("rep_duration_frames", 0),
                source_fps=meta.get("source_fps", 30.0),
                angle_names=meta.get("angle_names", []),
                movement_signature=sig,
            )
        except Exception as e:
            logger.error("template_load_failed", path=str(path), error=str(e))
            return None


def _compute_angle_curves(
    landmarks: np.ndarray,
    exercise_id: Optional[str] = None,
) -> tuple[np.ndarray, List[str]]:
    """
    Compute angle time series from landmarks.
    Returns (n_frames, n_angles) array and list of angle names.
    """
    angle_defs = EXERCISE_ANGLES.get(exercise_id or "", DEFAULT_ANGLES)
    n_frames = landmarks.shape[0]
    n_angles = len(angle_defs)
    curves = np.zeros((n_frames, n_angles), dtype=np.float64)
    names = [f"a{a}_{b}_{c}" for a, b, c in angle_defs]

    for i in range(n_frames):
        lm = landmarks[i]
        if np.allclose(lm[:, :2], 0.0):
            curves[i] = np.nan
            continue
        for j, (a_idx, b_idx, c_idx) in enumerate(angle_defs):
            curves[i, j] = calculate_angle(lm[a_idx, :2], lm[b_idx, :2], lm[c_idx, :2])

    # Interpolate NaN gaps.
    for j in range(n_angles):
        col = curves[:, j]
        nans = np.isnan(col)
        if nans.any() and not nans.all():
            col[nans] = np.interp(np.where(nans)[0], np.where(~nans)[0], col[~nans])

    return curves, names


def _resample_curve(curve: np.ndarray, target_len: int) -> np.ndarray:
    """Resample a 1D array to a fixed length using linear interpolation."""
    if len(curve) == target_len:
        return curve.copy()
    x_old = np.linspace(0, 1, len(curve))
    x_new = np.linspace(0, 1, target_len)
    return np.interp(x_new, x_old, curve)


def _extract_reps(
    angle_curves: np.ndarray,
    phase_seq: PhaseSequence,
) -> List[np.ndarray]:
    """
    Extract individual rep angle curve segments.
    Each rep: valley → peak → next valley.
    Returns list of (rep_len, n_angles) arrays.
    """
    reps = []
    peaks = phase_seq.peak_frames
    valleys = phase_seq.valley_frames

    if len(peaks) == 0:
        return reps

    for i, peak in enumerate(peaks):
        # Find surrounding valleys.
        prev_valleys = valleys[valleys < peak]
        next_valleys = valleys[valleys > peak]
        start = prev_valleys[-1] if len(prev_valleys) > 0 else 0
        end = next_valleys[0] if len(next_valleys) > 0 else len(angle_curves) - 1
        if end - start < 3:
            continue
        reps.append(angle_curves[start:end + 1])

    return reps


def generate_template(
    landmarks: np.ndarray,
    exercise_id: str,
    fps: float = 30.0,
) -> Optional[MotionTemplate]:
    """
    Generate a MotionTemplate from a (N, 33, 4) landmark sequence.
    """
    # Step 1: Detect phases.
    phase_seq = detect_phases(landmarks, exercise_id, fps)

    if phase_seq.rep_count == 0:
        logger.warning("no_reps_detected", exercise=exercise_id)
        return None

    # Step 2: Compute angle curves.
    angle_curves, angle_names = _compute_angle_curves(landmarks, exercise_id)

    # Step 3: Extract individual reps.
    reps = _extract_reps(angle_curves, phase_seq)
    
    # Also extract landmark reps
    landmark_reps = []
    peaks = phase_seq.peak_frames
    valleys = phase_seq.valley_frames
    for i, peak in enumerate(peaks):
        prev_valleys = valleys[valleys < peak]
        next_valleys = valleys[valleys > peak]
        start = prev_valleys[-1] if len(prev_valleys) > 0 else 0
        end = next_valleys[0] if len(next_valleys) > 0 else len(angle_curves) - 1
        if end - start >= 3:
            landmark_reps.append(landmarks[start:end + 1])

    if not reps or not landmark_reps:
        logger.warning("no_reps_extracted", exercise=exercise_id)
        return None

    # Step 4: Resample each rep to CANONICAL_REP_STEPS and average.
    n_angles = angle_curves.shape[1]
    canonical = np.zeros((n_angles, CANONICAL_REP_STEPS), dtype=np.float64)

    for angle_idx in range(n_angles):
        resampled_reps = []
        for rep in reps:
            curve = rep[:, angle_idx]
            resampled = _resample_curve(curve, CANONICAL_REP_STEPS)
            resampled_reps.append(resampled)
        canonical[angle_idx] = np.mean(resampled_reps, axis=0)
        
    canonical_lm = np.zeros((33, 4, CANONICAL_REP_STEPS), dtype=np.float64)
    for lm_idx in range(33):
        for coord in range(4):
            resampled_reps = []
            for rep in landmark_reps:
                curve = rep[:, lm_idx, coord]
                resampled = _resample_curve(curve, CANONICAL_REP_STEPS)
                resampled_reps.append(resampled)
            canonical_lm[lm_idx, coord] = np.mean(resampled_reps, axis=0)

    # Step 5: Compute angle ranges.
    angle_ranges = {}
    for j, name in enumerate(angle_names):
        col = angle_curves[:, j]
        valid = col[~np.isnan(col)]
        if len(valid) > 0:
            angle_ranges[name] = (float(np.min(valid)), float(np.max(valid)))

    # Step 6: Compute phase boundaries (normalized).
    avg_rep_frames = np.mean([len(r) for r in reps])
    phase_boundaries = []
    for phase in phase_seq.phases:
        if phase.label in (PhaseLabel.CONCENTRIC, PhaseLabel.PEAK, PhaseLabel.ECCENTRIC):
            start_pct = phase.start_frame / len(landmarks)
            end_pct = phase.end_frame / len(landmarks)
            phase_boundaries.append((start_pct, end_pct, phase.label.value))

    # Step 7: Movement signature — mean + std of canonical angles.
    sig_parts = []
    for j in range(n_angles):
        sig_parts.extend([
            np.mean(canonical[j]),
            np.std(canonical[j]),
            np.min(canonical[j]),
            np.max(canonical[j]),
        ])
    movement_signature = np.array(sig_parts, dtype=np.float32)

    template = MotionTemplate(
        exercise_id=exercise_id,
        canonical_angles=canonical.astype(np.float32),
        canonical_landmarks=canonical_lm.astype(np.float32),
        angle_ranges=angle_ranges,
        phase_boundaries=phase_boundaries,
        rep_duration_frames=float(avg_rep_frames),
        source_fps=fps,
        angle_names=angle_names,
        movement_signature=movement_signature,
    )

    logger.info(
        "template_generated",
        exercise=exercise_id,
        reps_used=len(reps),
        avg_rep_frames=avg_rep_frames,
        n_angles=n_angles,
    )

    return template
