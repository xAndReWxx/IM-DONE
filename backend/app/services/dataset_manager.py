"""
============================================================
PhysioAI Pro V2 - DatasetManager
============================================================
PURPOSE
    On startup, scan the exercise_videos/ folder for *.mp4 files
    and auto-generate a landmark dataset JSON for each one if it
    doesn't already exist (or if the video has changed).

    The generated dataset gives the exercise correction engine a
    reference "ideal form" to compare against live poses.

DATASET JSON FORMAT
    {
      "exercise_id": "chin_tuck",
      "video_file":  "chin_tuck.mp4",
      "generated_at": "2026-01-01T00:00:00",
      "file_hash": "<md5 of video bytes>",
      "frames": [
        {
          "frame_idx": 0,
          "landmarks": [[x,y,z,v]×33],
          "angles": {"spine": 0.0, "neck": 0.0, ...},
          "timestamp_ms": 0
        }
      ],
      "summary": {"total_frames": N, "duration_s": N, "key_angles": {...}},
      "tolerances": {"spine_angle": 15.0, "neck_angle": 10.0, ...}
    }

NON-BLOCKING
    All I/O and MediaPipe inference run in asyncio.to_thread so
    the event loop stays unblocked during startup.
============================================================
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Paths relative to the backend/ directory.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # → physioai-v2/backend/
_VIDEO_DIR    = _BACKEND_ROOT / "exercise_videos"
_DATASET_DIR  = _BACKEND_ROOT / "exercise_datasets"

# Default tolerance values (degrees) for each angle type.
_DEFAULT_TOLERANCES = {
    "spine_angle":  15.0,
    "neck_angle":   10.0,
    "shoulder_tilt": 8.0,
}


class DatasetManager:
    """
    Scans exercise_videos/ and generates / validates per-exercise
    landmark datasets in exercise_datasets/.
    """

    def __init__(self) -> None:
        _VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        _DATASET_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public API ──

    async def scan_and_generate(self) -> None:
        """
        Find all *.mp4 files in exercise_videos/ and ensure each has
        an up-to-date dataset. Runs non-blocking in a thread.
        """
        import asyncio
        await asyncio.to_thread(self._scan_and_generate_sync)

    def load_dataset(self, exercise_id: str) -> Optional[dict]:
        """
        Load the dataset for the given exercise_id.
        Returns None if no dataset exists yet.
        """
        path = _DATASET_DIR / f"{exercise_id}_dataset.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("dataset_load_failed", extra={"exercise_id": exercise_id, "error": str(e)})
            return None

    # ── Internal sync work ──

    def _scan_and_generate_sync(self) -> None:
        """Synchronous scan — called from asyncio.to_thread."""
        mp4_files = list(_VIDEO_DIR.glob("*.mp4"))
        if not mp4_files:
            logger.info("dataset_manager: no exercise videos found in %s", _VIDEO_DIR)
            return

        for video_path in mp4_files:
            exercise_id = video_path.stem  # e.g. "chin_tuck"
            dataset_path = _DATASET_DIR / f"{exercise_id}_dataset.json"

            try:
                video_hash = self._md5(video_path)
            except Exception as e:
                logger.warning("dataset_manager: cannot hash %s: %s", video_path.name, e)
                continue

            # Check if dataset is up-to-date.
            if dataset_path.exists():
                try:
                    with open(dataset_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    if existing.get("file_hash") == video_hash:
                        logger.info("dataset_manager: %s dataset is current, skipping", exercise_id)
                        continue
                    else:
                        logger.info("dataset_manager: %s video changed, regenerating", exercise_id)
                except Exception:
                    pass  # Corrupt / unreadable dataset — regenerate.

            logger.info("dataset_manager: generating dataset for %s", exercise_id)
            dataset = self._generate_dataset(video_path, exercise_id, video_hash)
            if dataset is not None:
                self._save_dataset(dataset, dataset_path)
                logger.info(
                    "dataset_manager: saved %s (%d frames)",
                    dataset_path.name,
                    len(dataset.get("frames", [])),
                )

    def _generate_dataset(
        self,
        video_path: Path,
        exercise_id: str,
        file_hash: str,
    ) -> Optional[dict]:
        """
        Process a video file frame-by-frame with MediaPipe and build
        the dataset dict. Returns None if processing fails.
        """
        try:
            import cv2
        except ImportError:
            logger.warning("dataset_manager: OpenCV not available, cannot generate dataset")
            return None

        try:
            from app.services.ai.pose_engine import PoseEngine
            from app.services.ai.geometry import vertical_angle, horizontal_tilt, midpoint
        except Exception as e:
            logger.warning("dataset_manager: AI imports failed: %s", e)
            return None

        # Lazily initialize a PoseEngine just for dataset generation.
        engine = PoseEngine()
        try:
            engine.initialize()
        except Exception as e:
            logger.warning("dataset_manager: PoseEngine init failed: %s", e)
            return None

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.warning("dataset_manager: cannot open video %s", video_path.name)
            return None

        fps_video = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        frames: List[dict] = []
        frame_idx = 0

        while True:
            ret, bgr = cap.read()
            if not ret:
                break

            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            try:
                landmarks_arr = engine.detect(rgb)
            except Exception:
                frame_idx += 1
                continue

            if landmarks_arr is None or landmarks_arr.shape[0] < 33:
                frame_idx += 1
                continue

            # Compute a small set of diagnostic angles.
            try:
                LM_LEFT_EAR, LM_RIGHT_EAR = 7, 8
                LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER = 11, 12
                LM_LEFT_HIP, LM_RIGHT_HIP = 23, 24

                sh_l   = landmarks_arr[LM_LEFT_SHOULDER][:2]
                sh_r   = landmarks_arr[LM_RIGHT_SHOULDER][:2]
                ear_l  = landmarks_arr[LM_LEFT_EAR][:2]
                ear_r  = landmarks_arr[LM_RIGHT_EAR][:2]
                hip_l  = landmarks_arr[LM_LEFT_HIP][:2]
                hip_r  = landmarks_arr[LM_RIGHT_HIP][:2]

                neck_angle   = float((vertical_angle(ear_l, sh_l) + vertical_angle(ear_r, sh_r)) / 2.0)
                shoulder_tilt = float(horizontal_tilt(sh_l, sh_r))
                spine_angle  = float(vertical_angle(midpoint(sh_l, sh_r), midpoint(hip_l, hip_r)))
            except Exception:
                neck_angle = shoulder_tilt = spine_angle = 0.0

            frames.append({
                "frame_idx": frame_idx,
                "landmarks": landmarks_arr.tolist(),
                "angles": {
                    "neck_angle":    round(neck_angle, 3),
                    "spine_angle":   round(spine_angle, 3),
                    "shoulder_tilt": round(shoulder_tilt, 3),
                },
                "timestamp_ms": round(frame_idx / fps_video * 1000),
            })
            frame_idx += 1

        cap.release()
        engine.close()

        if not frames:
            logger.warning("dataset_manager: no valid frames extracted from %s", video_path.name)
            return None

        # Validate: need at least 5 valid frames.
        if len(frames) < 5:
            logger.warning(
                "dataset_manager: only %d valid frames extracted from %s, skipping",
                len(frames), video_path.name,
            )
            return None

        # Compute summary statistics.
        all_neck  = [f["angles"]["neck_angle"]    for f in frames]
        all_spine = [f["angles"]["spine_angle"]   for f in frames]
        all_tilt  = [f["angles"]["shoulder_tilt"] for f in frames]

        import statistics as stats
        summary = {
            "total_frames": len(frames),
            "duration_s": round(len(frames) / fps_video, 2),
            "key_angles": {
                "neck_angle":    {"mean": round(stats.mean(all_neck), 2),  "stdev": round(stats.stdev(all_neck) if len(all_neck) > 1 else 0.0, 2)},
                "spine_angle":   {"mean": round(stats.mean(all_spine), 2), "stdev": round(stats.stdev(all_spine) if len(all_spine) > 1 else 0.0, 2)},
                "shoulder_tilt": {"mean": round(stats.mean(all_tilt), 2),  "stdev": round(stats.stdev(all_tilt) if len(all_tilt) > 1 else 0.0, 2)},
            },
        }

        return {
            "exercise_id":  exercise_id,
            "video_file":   video_path.name,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "file_hash":    file_hash,
            "frames":       frames,
            "summary":      summary,
            "tolerances":   _DEFAULT_TOLERANCES.copy(),
        }

    @staticmethod
    def _md5(path: Path) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _save_dataset(dataset: dict, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)


# ── Singleton ──
dataset_manager = DatasetManager()
