"""
============================================================
PhysioAI Pro V2 - Dataset Exporter
============================================================
PURPOSE
    Exports fully-processed exercise data into structured JSON
    format for downstream AI consumption.

OUTPUT FORMAT
    {
      "exercise": "t_fly",
      "fps": 30.0,
      "frame_count": 240,
      "duration_seconds": 8.0,
      "resolution": "640x480",
      "failed_frames": 2,
      "normalization": {
        "method": "hip_center_torso_scale",
        "smoothing": "ema_0.6"
      },
      "angle_names": ["neck_left", "neck_right", ...],
      "angle_ranges": {
        "neck_left": {"min": 14.2, "max": 38.1},
        ...
      },
      "phases": [
        {
          "label": "concentric",
          "start_frame": 15,
          "end_frame": 42,
          "start_time": 0.5,
          "end_time": 1.4
        },
        ...
      ],
      "rep_count": 5,
      "frames": [
        {
          "frame": 0,
          "timestamp": 0.0,
          "phase": "rest",
          "landmarks": [[x,y,z,vis], ...],  // 33 entries
          "angles": {"neck_left": 22.3, ...}
        },
        ...
      ]
    }

STORAGE
    Datasets saved to exercise_datasets/ directory.
    One JSON file per exercise video.
============================================================
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from app.services.exercise_engine.video_processor import VideoMetadata
from app.services.exercise_engine.phase_detector import (
    PhaseSequence,
    get_per_frame_labels,
    PhaseLabel,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Phase integer → label string mapping.
_PHASE_INT_TO_STR = {
    0: "rest",
    1: "concentric",
    2: "peak",
    3: "eccentric",
}


def export_dataset(
    metadata: VideoMetadata,
    normalized_landmarks: np.ndarray,
    angles: Dict[str, np.ndarray],
    phase_seq: PhaseSequence,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Export a complete exercise dataset to JSON.

    Args:
        metadata: Video metadata.
        normalized_landmarks: (N, 33, 4) normalized landmarks.
        angles: Dict of angle_name → (N,) arrays.
        phase_seq: Detected phase sequence.
        output_dir: Where to save. Defaults to exercise_datasets/.

    Returns:
        Path to the saved JSON file.
    """
    if output_dir is None:
        backend_root = Path(__file__).resolve().parent.parent.parent.parent
        output_dir = backend_root / "exercise_datasets"
    output_dir.mkdir(parents=True, exist_ok=True)

    n_frames = normalized_landmarks.shape[0]
    fps = metadata.fps

    # Per-frame phase labels.
    frame_labels = get_per_frame_labels(phase_seq, n_frames)

    # Angle names.
    angle_names = sorted(angles.keys())

    # Angle ranges.
    angle_ranges = {}
    for name in angle_names:
        values = angles[name]
        valid = values[~np.isnan(values)] if np.any(np.isnan(values)) else values
        if len(valid) > 0:
            angle_ranges[name] = {
                "min": round(float(np.min(valid)), 2),
                "max": round(float(np.max(valid)), 2),
                "mean": round(float(np.mean(valid)), 2),
                "std": round(float(np.std(valid)), 2),
            }

    # Phase summaries.
    phases_list = []
    for phase in phase_seq.phases:
        phases_list.append({
            "label": phase.label.value,
            "start_frame": int(phase.start_frame),
            "end_frame": int(phase.end_frame),
            "start_time": round(float(phase.start_frame) / fps, 3),
            "end_time": round(float(phase.end_frame) / fps, 3),
        })

    # Default metadata based on exercise ID
    ex_meta = {
        "difficulty": "unknown",
        "movement_type": "unknown",
        "target_posture_issue": [],
        "target_muscles": [],
        "recommended_rom": {},
        "name_en": metadata.exercise_id.replace("_", " ").title(),
        "name_ar": metadata.exercise_id.replace("_", " ").title(),
        "description": "Auto-generated exercise.",
        "reps": 10,
        "duration_s": 60,
        "instructions_ar": [],
    }

    # Try to load dynamic metadata from exercise_videos/{exercise_id}/metadata.json
    video_dir = metadata.path.parent
    if video_dir.name == metadata.exercise_id:
        # It's inside a folder named after the exercise
        meta_file = video_dir / "metadata.json"
    else:
        # Or maybe right next to the video
        meta_file = video_dir / f"{metadata.exercise_id}_metadata.json"
        if not meta_file.exists():
            # Try a subfolder
            meta_file = video_dir / metadata.exercise_id / "metadata.json"

    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                loaded_meta = json.load(f)
                ex_meta.update(loaded_meta)
        except Exception as e:
            logger.error("metadata_load_failed", file=str(meta_file), error=str(e))
    else:
        # Fallback hardcoded defaults if no JSON is found
        metadata_info = {
            "t_fly": {
                "difficulty": "beginner",
                "movement_type": "mobility",
                "target_posture_issue": ["rounded_shoulders", "forward_head"],
                "target_muscles": ["rear_delts", "traps", "rhomboids"],
                "name_en": "T-Fly",
                "name_ar": "تمرين حرف T",
                "reps": 10,
                "duration_s": 60,
            },
            "shoulder_release": {
                "difficulty": "beginner",
                "movement_type": "mobility",
                "target_posture_issue": ["rounded_shoulders", "tight_pecs", "uneven_shoulders"],
                "target_muscles": ["anterior_deltoids", "pectorals"],
                "name_en": "Shoulder Release",
                "name_ar": "تحرير الكتف",
                "reps": 10,
                "duration_s": 75,
            },
            "chin_tuck": {
                "difficulty": "beginner",
                "movement_type": "correction",
                "target_posture_issue": ["forward_head"],
                "target_muscles": ["deep_cervical_flexors"],
                "name_en": "Chin Tuck",
                "name_ar": "شد الذقن",
                "reps": 10,
                "duration_s": 60,
            }
        }
        if metadata.exercise_id in metadata_info:
            ex_meta.update(metadata_info[metadata.exercise_id])

    # Per-frame data.
    frames_data: List[dict] = []
    for i in range(n_frames):
        frame_entry = {
            "frame": i,
            "timestamp": round(i / fps, 4),
            "phase": _PHASE_INT_TO_STR.get(int(frame_labels[i]), "rest"),
            "landmarks": normalized_landmarks[i].tolist(),
            "angles": {
                name: round(float(angles[name][i]), 2) for name in angle_names
            },
        }
        frames_data.append(frame_entry)

    # Assemble the dataset.
    dataset = {
        "exercise": metadata.exercise_id,
        "fps": round(fps, 2),
        "frame_count": n_frames,
        "duration_seconds": round(n_frames / fps, 2),
        "resolution": f"{metadata.width}x{metadata.height}",
        "source_video": metadata.path.name,
        "metadata": ex_meta,
        "normalization": {
            "method": "hip_center_torso_scale",
            "smoothing": "ema_0.6",
            "interpolation": "linear",
        },
        "angle_names": angle_names,
        "angle_ranges": angle_ranges,
        "phases": phases_list,
        "rep_count": int(phase_seq.rep_count),
        "frames": frames_data,
    }

    # Save.
    output_path = output_dir / f"{metadata.exercise_id}.json"
    output_path.write_text(
        json.dumps(dataset, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(
        "dataset_exported",
        exercise=metadata.exercise_id,
        path=str(output_path),
        frames=n_frames,
        reps=phase_seq.rep_count,
        phases=len(phases_list),
        size_mb=f"{file_size_mb:.2f}",
    )

    return output_path


def export_compact_npz(
    metadata: VideoMetadata,
    normalized_landmarks: np.ndarray,
    angles: Dict[str, np.ndarray],
    phase_seq: PhaseSequence,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Export a compact .npz binary for fast loading (used by the
    MotionTemplate generator and realtime comparison engine).
    """
    if output_dir is None:
        backend_root = Path(__file__).resolve().parent.parent.parent.parent
        output_dir = backend_root / "exercise_datasets"
    output_dir.mkdir(parents=True, exist_ok=True)

    n_frames = normalized_landmarks.shape[0]
    frame_labels = get_per_frame_labels(phase_seq, n_frames)

    # Stack angle arrays into a single matrix.
    angle_names = sorted(angles.keys())
    angle_matrix = np.column_stack([angles[name] for name in angle_names])

    output_path = output_dir / f"{metadata.exercise_id}.npz"
    np.savez_compressed(
        output_path,
        landmarks=normalized_landmarks,
        angles=angle_matrix,
        angle_names=np.array(angle_names),
        phase_labels=frame_labels,
        fps=np.float32(metadata.fps),
        frame_count=np.int32(n_frames),
        rep_count=np.int32(phase_seq.rep_count),
    )

    logger.info(
        "compact_dataset_exported",
        exercise=metadata.exercise_id,
        path=str(output_path),
    )

    return output_path
