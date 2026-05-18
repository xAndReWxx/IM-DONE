"""
============================================================
PhysioAI Pro V2 - Video Processor
============================================================
PURPOSE
    Loads exercise video files frame-by-frame using OpenCV,
    runs MediaPipe Pose on each frame, and returns raw
    landmark arrays with metadata.

FEATURES
    - Supports .mp4, .mov, .avi
    - Handles failed frames gracefully (returns None)
    - Reports progress via callback
    - Extracts video metadata (fps, resolution, duration)

COORDINATES
    Raw MediaPipe output: x,y ∈ [0,1], z = relative depth,
    visibility ∈ [0,1]. Not yet normalized.
============================================================
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Supported video extensions.
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}


@dataclass
class VideoMetadata:
    """Metadata extracted from a video file."""
    path: Path
    fps: float
    width: int
    height: int
    total_frames: int
    duration_seconds: float
    exercise_id: str


@dataclass
class VideoProcessingResult:
    """Output of processing a single video."""
    metadata: VideoMetadata
    # (N, 33, 4) — raw MediaPipe landmarks. Frames where
    # detection failed have all-zero rows.
    raw_landmarks: np.ndarray
    # Boolean mask: True = valid detection, False = failed.
    valid_mask: np.ndarray
    # Number of frames that failed detection.
    failed_frames: int


def _infer_exercise_id(video_path: Path) -> str:
    """
    Infer exercise ID from file/folder naming.

    Strategy:
      1. If parent folder != 'exercise_videos', use parent name.
      2. Otherwise use the stem of the file.
    Normalize: lowercase, spaces/hyphens → underscores.
    """
    parent_name = video_path.parent.name
    if parent_name.lower() not in ("exercise_videos", "videos", ""):
        name = parent_name
    else:
        name = video_path.stem

    return name.lower().replace(" ", "_").replace("-", "_")


def discover_videos(videos_dir: Path) -> List[Path]:
    """
    Find all exercise video files in a directory (recursive).
    Returns sorted list of absolute paths.
    """
    results = []
    for ext in VIDEO_EXTENSIONS:
        results.extend(videos_dir.rglob(f"*{ext}"))
    return sorted(set(results))


def process_video(
    video_path: Path,
    max_frames: int = 5000,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Optional[VideoProcessingResult]:
    """
    Process a single video through MediaPipe Pose.

    Args:
        video_path: Path to the video file.
        max_frames: Safety cap on frames to process.
        progress_callback: fn(current_frame, total_frames) for progress.

    Returns:
        VideoProcessingResult or None on failure.
    """
    try:
        import cv2
    except ImportError:
        logger.error("opencv_not_available")
        return None

    try:
        import mediapipe as mp
    except ImportError:
        logger.error("mediapipe_not_available")
        return None

    if not video_path.exists():
        logger.error("video_not_found", path=str(video_path))
        return None

    # ── Open video ──
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error("video_open_failed", path=str(video_path))
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    total_frames = min(total_frames, max_frames)

    exercise_id = _infer_exercise_id(video_path)

    metadata = VideoMetadata(
        path=video_path,
        fps=fps,
        width=width,
        height=height,
        total_frames=total_frames,
        duration_seconds=total_frames / fps if fps > 0 else 0.0,
        exercise_id=exercise_id,
    )

    logger.info(
        "video_processing_start",
        video=video_path.name,
        exercise=exercise_id,
        fps=fps,
        frames=total_frames,
        resolution=f"{width}x{height}",
    )

    # ── Initialize MediaPipe ──
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

    all_landmarks: List[np.ndarray] = []
    valid_mask: List[bool] = []
    failed_count = 0

    try:
        for frame_idx in range(total_frames):
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
                all_landmarks.append(lm_array)
                valid_mask.append(True)
            else:
                # Failed detection — insert placeholder.
                all_landmarks.append(np.zeros((33, 4), dtype=np.float32))
                valid_mask.append(False)
                failed_count += 1

            if progress_callback and frame_idx % 10 == 0:
                progress_callback(frame_idx + 1, total_frames)

    finally:
        cap.release()
        landmarker.close()

    if not all_landmarks:
        logger.warning("no_frames_extracted", video=video_path.name)
        return None

    logger.info(
        "video_processing_complete",
        video=video_path.name,
        exercise=exercise_id,
        frames_total=len(all_landmarks),
        frames_failed=failed_count,
        success_rate=f"{(1 - failed_count / max(1, len(all_landmarks))) * 100:.1f}%",
    )

    return VideoProcessingResult(
        metadata=metadata,
        raw_landmarks=np.array(all_landmarks, dtype=np.float32),
        valid_mask=np.array(valid_mask, dtype=bool),
        failed_frames=failed_count,
    )
