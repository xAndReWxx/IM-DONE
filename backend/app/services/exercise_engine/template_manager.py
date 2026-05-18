"""
============================================================
PhysioAI Pro V2 - Template Manager
============================================================
PURPOSE
    Singleton that manages loading, caching, and generating
    MotionTemplates from exercise reference videos.

    On startup, it scans the datasets/ directory for pre-built
    templates. If a video exists but no template, it can generate
    one on demand.

USAGE
    manager = TemplateManager(videos_dir, datasets_dir)
    await manager.initialize()
    template = manager.get("chin_tuck")
============================================================
"""

import asyncio
from pathlib import Path
from typing import Dict, Optional

from app.services.exercise_engine.motion_template import (
    MotionTemplate,
    generate_template,
)
from app.services.exercise_engine.dataset_processor import (
    process_video,
)
from app.utils.logger import get_logger

import numpy as np

logger = get_logger(__name__)


class TemplateManager:
    """
    Manages loading and caching of MotionTemplates.
    """

    def __init__(
        self,
        videos_dir: Optional[Path] = None,
        datasets_dir: Optional[Path] = None,
    ) -> None:
        # Default paths relative to backend root.
        backend_root = Path(__file__).resolve().parent.parent.parent.parent
        self._videos_dir = videos_dir or (backend_root / "exercise_videos")
        self._datasets_dir = datasets_dir or (self._videos_dir / "datasets")
        self._templates: Dict[str, MotionTemplate] = {}
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def available_exercises(self) -> list[str]:
        """Return IDs of exercises that have loaded templates."""
        return list(self._templates.keys())

    def get(self, exercise_id: str) -> Optional[MotionTemplate]:
        """Get a cached MotionTemplate by exercise ID."""
        return self._templates.get(exercise_id)

    async def initialize(self) -> None:
        """Load all pre-built templates from the datasets directory."""
        if self._initialized:
            return

        self._datasets_dir.mkdir(parents=True, exist_ok=True)

        # Load any existing templates.
        loaded = 0
        for json_file in self._datasets_dir.glob("*.json"):
            template = await asyncio.to_thread(
                MotionTemplate.load, json_file.with_suffix("")
            )
            if template:
                self._templates[template.exercise_id] = template
                loaded += 1
                logger.info(
                    "template_loaded",
                    exercise=template.exercise_id,
                    path=str(json_file),
                )

        self._initialized = True
        logger.info(
            "template_manager_ready",
            loaded=loaded,
            datasets_dir=str(self._datasets_dir),
            available=list(self._templates.keys()),
        )

    async def generate_from_video(
        self,
        exercise_id: str,
        video_filename: Optional[str] = None,
    ) -> Optional[MotionTemplate]:
        """
        Process a video and generate a template.

        Args:
            exercise_id: Stable exercise ID (e.g. "chin_tuck")
            video_filename: Video file name (defaults to exercise_id.mp4)
        """
        filename = video_filename or f"{exercise_id}.mp4"
        video_path = self._videos_dir / filename

        if not video_path.exists():
            logger.warning("video_not_found", exercise=exercise_id, path=str(video_path))
            return None

        # Step 1: Process video → landmarks .npz
        npz_path = await asyncio.to_thread(
            process_video, video_path, self._datasets_dir
        )
        if npz_path is None:
            return None

        # Step 2: Load landmarks.
        data = np.load(npz_path)
        landmarks = data["landmarks"]
        fps = float(data["fps"])

        # Step 3: Generate template.
        template = await asyncio.to_thread(
            generate_template, landmarks, exercise_id, fps
        )
        if template is None:
            return None

        # Step 4: Save template.
        template_path = self._datasets_dir / exercise_id
        await asyncio.to_thread(template.save, template_path)

        # Step 5: Cache it.
        self._templates[exercise_id] = template
        logger.info("template_generated_and_cached", exercise=exercise_id)

        return template

    async def generate_all(self) -> int:
        """
        Generate templates for all videos in the videos directory.
        Returns the count of successfully generated templates.
        """
        count = 0
        for video_file in sorted(self._videos_dir.glob("*.mp4")):
            exercise_id = video_file.stem
            template = await self.generate_from_video(exercise_id, video_file.name)
            if template:
                count += 1
        return count


# ── Singleton ──
template_manager = TemplateManager()
