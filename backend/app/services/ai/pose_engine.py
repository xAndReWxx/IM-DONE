"""
============================================================
PhysioAI Pro V2 - MediaPipe Pose Engine
============================================================
PURPOSE
    Thin wrapper around MediaPipe's PoseLandmarker. Handles:
      • Model download (once, cached to disk)
      • Engine initialization with sane defaults
      • Synchronous-style inference (we drive realtime via
        IMAGE mode, not LIVE_STREAM async, because the WS
        already gives us an asyncio-based realtime flow)

DESIGN DECISIONS
    • Using mediapipe.tasks.python.vision.PoseLandmarker (modern
      API), NOT the legacy mp.solutions.pose. The tasks API is
      what Google recommends going forward.
    • RunningMode.IMAGE is simpler than LIVE_STREAM and easier
      to integrate with FastAPI's per-request flow. Latency is
      essentially the same at <=20 FPS.
    • If MediaPipe isn't installed (e.g. during early dev), the
      class falls back to no-op detection so the rest of the
      stack still boots — useful when iterating on the UI alone.
============================================================
"""

import os
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


# Where we cache the downloaded model.
MODEL_CACHE_DIR = Path(__file__).resolve().parents[2] / "models_cache"
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_CACHE_DIR / settings.mediapipe_model_filename


# ── Try to import MediaPipe. Don't crash if missing. ──
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    logger.warning("mediapipe_not_installed")


def _download_model_if_missing() -> None:
    """One-time download of the pose-landmarker model."""
    if MODEL_PATH.exists():
        return
    logger.info("mediapipe_model_downloading", url=settings.mediapipe_model_url)
    try:
        urllib.request.urlretrieve(settings.mediapipe_model_url, str(MODEL_PATH))
        logger.info("mediapipe_model_downloaded", path=str(MODEL_PATH))
    except Exception as e:
        logger.error("mediapipe_model_download_failed", error=str(e))
        raise


class PoseEngine:
    """
    Wraps MediaPipe PoseLandmarker. One shared instance is enough —
    inference is stateless given a single image (no per-stream state).
    """

    def __init__(self) -> None:
        self._landmarker = None
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    def initialize(self) -> None:
        """
        Synchronous one-time setup. Safe to call multiple times.
        """
        if self._ready:
            return

        if not MEDIAPIPE_AVAILABLE:
            logger.warning("mediapipe_disabled", reason="package_not_installed")
            return

        _download_model_if_missing()

        base_options = mp_python.BaseOptions(model_asset_path=str(MODEL_PATH))
        options = mp_vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.IMAGE,
            # Raised from 0.5 → 0.6 for better stability during
            # side-profile scans. Higher values reduce false
            # detections but MediaPipe still tracks profiles well
            # at 0.6. Going above 0.7 risks dropping side views.
            min_pose_detection_confidence=0.6,
            min_pose_presence_confidence=0.6,
            min_tracking_confidence=0.6,
            output_segmentation_masks=False,
            # Note: num_poses=1 is default; we only track one person.
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        self._ready = True
        logger.info("mediapipe_ready", model=settings.mediapipe_model_filename)

    def detect(self, rgb_frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Run pose inference on a single RGB frame.

        Args:
            rgb_frame: HxWx3 numpy array, uint8, RGB color order.

        Returns:
            (33, 4) numpy array of [x, y, z, visibility] for the first
            detected person, or None if no person was detected.
        """
        if not self._ready or self._landmarker is None:
            return None

        # MediaPipe expects an mp.Image wrapper, not a raw ndarray.
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._landmarker.detect(mp_image)

        if not result.pose_landmarks:
            return None

        first_person = result.pose_landmarks[0]
        return np.array(
            [[lm.x, lm.y, lm.z, lm.visibility] for lm in first_person],
            dtype=np.float32,
        )

    def close(self) -> None:
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:
                pass
        self._landmarker = None
        self._ready = False
