"""
============================================================
PhysioAI Pro V2 - Dataset Processor
============================================================
PURPOSE
    Process exercise reference videos through MediaPipe Pose,
    extracting per-frame landmark arrays. This is the raw data
    foundation for all downstream analysis.

PIPELINE
    video file → frame iterator → MediaPipe detection →
    raw_landmarks (N_frames × 33 × 4) → saved .npz

NORMALIZATION
    Each frame's landmarks are normalized to be translation-
    and scale-invariant by:
      1. Centering on the hip midpoint
      2. Scaling so shoulder-hip distance = 1.0

    This makes the dataset usable regardless of camera
    distance, body size, or position in frame.
============================================================
"""

from pathlib import Path
from typing import Optional

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)

# MediaPipe landmark indices for normalization anchors.
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24


def _normalize_frame(landmarks: np.ndarray) -> np.ndarray:
    """
    Normalize a (33, 4) landmark array:
      - Center on hip midpoint (x, y)
      - Scale so average shoulder-hip distance = 1.0
      - Preserve visibility in column 3
    """
    lm = landmarks.copy()
    # Hip midpoint for centering.
    hip_mid = (lm[LM_LEFT_HIP, :2] + lm[LM_RIGHT_HIP, :2]) / 2.0
    lm[:, 0] -= hip_mid[0]
    lm[:, 1] -= hip_mid[1]

    # Scale: average distance from shoulder to hip.
    sh_mid = (lm[LM_LEFT_SHOULDER, :2] + lm[LM_RIGHT_SHOULDER, :2]) / 2.0
    hip_mid_centered = np.array([0.0, 0.0])  # now centered
    scale = np.linalg.norm(sh_mid - hip_mid_centered) + 1e-6
    lm[:, :3] /= scale  # scale x, y, z

    return lm


def process_video(
    video_path: Path,
    output_dir: Optional[Path] = None,
    max_frames: int = 3000,
) -> Optional[Path]:
    """
    Process a video file → extract normalized landmarks → save as .npz.

    Returns the path to the saved .npz file, or None on failure.
    The .npz contains:
        'landmarks': (N, 33, 4) float32 — normalized landmarks
        'fps': float — source video FPS
        'frame_count': int — total frames extracted
    """
    try:
        import cv2
    except ImportError:
        logger.error("opencv_not_available", path=str(video_path))
        return None

    try:
        import mediapipe as mp
    except ImportError:
        logger.error("mediapipe_not_available", path=str(video_path))
        return None

    if not video_path.exists():
        logger.error("video_not_found", path=str(video_path))
        return None

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error("video_open_failed", path=str(video_path))
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # Initialize MediaPipe Pose using the new Tasks API.
    # We load the model from the cache dir that PoseEngine uses.
    try:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
    except ImportError:
        logger.error("mediapipe_tasks_not_available", path=str(video_path))
        return None

    # Find the model.
    backend_root = Path(__file__).resolve().parent.parent.parent.parent
    model_path = backend_root / "app" / "models_cache" / "pose_landmarker_full.task"
    if not model_path.exists():
        logger.error("mediapipe_model_not_found", path=str(model_path))
        return None

    base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
    options = mp_vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.IMAGE,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = mp_vision.PoseLandmarker.create_from_options(options)

    all_landmarks = []
    frame_idx = 0

    try:
        while frame_idx < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect(mp_image)

            if result.pose_landmarks:
                first_person = result.pose_landmarks[0]
                lm_array = np.array(
                    [[lm.x, lm.y, lm.z, lm.visibility]
                     for lm in first_person],
                    dtype=np.float32,
                )
                normalized = _normalize_frame(lm_array)
                all_landmarks.append(normalized)
            else:
                # No detection — insert zeros (will be filtered later).
                all_landmarks.append(np.zeros((33, 4), dtype=np.float32))

            frame_idx += 1
    finally:
        cap.release()
        landmarker.close()

    if not all_landmarks:
        logger.warning("no_landmarks_extracted", path=str(video_path))
        return None

    landmarks_array = np.array(all_landmarks, dtype=np.float32)

    # Save output.
    if output_dir is None:
        output_dir = video_path.parent / "datasets"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_path.stem}.npz"

    np.savez_compressed(
        output_path,
        landmarks=landmarks_array,
        fps=np.float32(fps),
        frame_count=np.int32(len(all_landmarks)),
    )

    logger.info(
        "video_processed",
        video=video_path.name,
        frames=len(all_landmarks),
        fps=fps,
        output=str(output_path),
    )
    return output_path


def process_all_videos(
    videos_dir: Path,
    output_dir: Optional[Path] = None,
) -> list[Path]:
    """Process all .mp4 files in a directory. Returns list of saved .npz paths."""
    results = []
    for video_file in sorted(videos_dir.glob("*.mp4")):
        out = process_video(video_file, output_dir)
        if out:
            results.append(out)
    return results
