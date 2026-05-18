"""
============================================================
PhysioAI Pro V2 - Dataset Generator
============================================================
PURPOSE
    Master orchestrator for the complete exercise dataset
    generation pipeline:

      VIDEO → LANDMARKS → NORMALIZE → ANGLES → PHASES →
      TEMPLATE → EXPORT (JSON + NPZ)

    Processes all videos in exercise_videos/ and outputs to
    exercise_datasets/.

USAGE
    from app.services.exercise_engine.dataset_generator import (
        generate_all_datasets,
    )
    results = generate_all_datasets()

    Or via CLI:
    python -m app.scripts.generate_datasets
============================================================
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import time

from app.services.exercise_engine.video_processor import (
    discover_videos,
    process_video,
    VideoProcessingResult,
)
from app.services.exercise_engine.landmark_normalizer import (
    normalize_landmarks,
)
from app.services.exercise_engine.angle_extractor import (
    extract_angles,
)
from app.services.exercise_engine.phase_detector import (
    detect_phases,
    PhaseSequence,
)
from app.services.exercise_engine.motion_template import (
    generate_template,
    MotionTemplate,
)
from app.services.exercise_engine.dataset_exporter import (
    export_dataset,
    export_compact_npz,
)
from app.services.exercise_engine.dataset_quality_validator import (
    validate_dataset,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GenerationResult:
    """Result of generating a dataset for one exercise."""
    exercise_id: str
    success: bool
    json_path: Optional[Path] = None
    npz_path: Optional[Path] = None
    template: Optional[MotionTemplate] = None
    frame_count: int = 0
    rep_count: int = 0
    failed_frames: int = 0
    processing_time: float = 0.0
    error: Optional[str] = None


def generate_single_dataset(
    video_path: Path,
    output_dir: Optional[Path] = None,
    templates_dir: Optional[Path] = None,
    progress_callback=None,
) -> GenerationResult:
    """
    Full pipeline for a single exercise video.

    Steps:
      1. Process video → raw landmarks
      2. Normalize landmarks
      3. Extract joint angles
      4. Detect movement phases
      5. Generate motion template
      6. Export JSON dataset
      7. Export compact NPZ
    """
    start_time = time.monotonic()

    # ── Step 1: Process video ──
    logger.info("pipeline_step", step=1, action="video_processing", video=video_path.name)
    result = process_video(video_path, progress_callback=progress_callback)

    if result is None:
        return GenerationResult(
            exercise_id=video_path.stem,
            success=False,
            error="Video processing failed",
        )

    exercise_id = result.metadata.exercise_id

    # ── Step 2: Normalize landmarks ──
    logger.info("pipeline_step", step=2, action="normalization", exercise=exercise_id)
    normalized = normalize_landmarks(result.raw_landmarks, result.valid_mask)
    
    # ── Step 3: Validate dataset quality ──
    logger.info("pipeline_step", step=3, action="validation", exercise=exercise_id)
    validation_result = validate_dataset(result.raw_landmarks, result.valid_mask, normalized)
    if not validation_result.is_valid:
        return GenerationResult(
            exercise_id=exercise_id,
            success=False,
            error=f"Dataset failed validation: {'; '.join(validation_result.failure_reasons)}"
        )

    # ── Step 4: Extract angles ──
    logger.info("pipeline_step", step=4, action="angle_extraction", exercise=exercise_id)
    angles = extract_angles(normalized)

    # ── Step 5: Detect phases ──
    logger.info("pipeline_step", step=5, action="phase_detection", exercise=exercise_id)
    phase_seq = detect_phases(normalized, exercise_id, result.metadata.fps)

    # ── Step 6: Generate motion template ──
    logger.info("pipeline_step", step=6, action="template_generation", exercise=exercise_id)
    template = generate_template(normalized, exercise_id, result.metadata.fps)
    if template and templates_dir:
        templates_dir.mkdir(parents=True, exist_ok=True)
        template.save(templates_dir / exercise_id)

    # ── Step 7: Export JSON ──
    logger.info("pipeline_step", step=7, action="json_export", exercise=exercise_id)
    json_path = export_dataset(
        result.metadata, normalized, angles, phase_seq, output_dir
    )

    # ── Step 8: Export NPZ ──
    logger.info("pipeline_step", step=8, action="npz_export", exercise=exercise_id)
    npz_path = export_compact_npz(
        result.metadata, normalized, angles, phase_seq, output_dir
    )

    elapsed = time.monotonic() - start_time

    logger.info(
        "pipeline_complete",
        exercise=exercise_id,
        frames=result.metadata.total_frames,
        reps=phase_seq.rep_count,
        failed=result.failed_frames,
        time_s=f"{elapsed:.2f}",
    )

    return GenerationResult(
        exercise_id=exercise_id,
        success=True,
        json_path=json_path,
        npz_path=npz_path,
        template=template,
        frame_count=normalized.shape[0],
        rep_count=phase_seq.rep_count,
        failed_frames=result.failed_frames,
        processing_time=elapsed,
    )


def generate_all_datasets(
    videos_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    templates_dir: Optional[Path] = None,
) -> List[GenerationResult]:
    """
    Process all exercise videos and generate datasets.

    Args:
        videos_dir: Directory containing exercise videos.
                    Defaults to backend/exercise_videos/.
        output_dir: Where to save JSON/NPZ datasets.
                    Defaults to backend/exercise_datasets/.
        templates_dir: Where to save motion templates.
                       Defaults to exercise_videos/datasets/.

    Returns:
        List of GenerationResult for each video processed.
    """
    backend_root = Path(__file__).resolve().parent.parent.parent.parent

    if videos_dir is None:
        videos_dir = backend_root / "exercise_videos"
    if output_dir is None:
        output_dir = backend_root / "exercise_datasets"
    if templates_dir is None:
        templates_dir = videos_dir / "datasets"

    # Discover all videos.
    video_files = discover_videos(videos_dir)

    if not video_files:
        logger.warning("no_videos_found", dir=str(videos_dir))
        return []

    logger.info(
        "dataset_generation_start",
        videos_found=len(video_files),
        videos_dir=str(videos_dir),
        output_dir=str(output_dir),
    )

    results: List[GenerationResult] = []
    total = len(video_files)

    for idx, video_path in enumerate(video_files, 1):
        logger.info(
            "processing_video",
            index=f"{idx}/{total}",
            video=video_path.name,
            exercise=video_path.parent.name,
        )

        def _progress(current: int, total_frames: int):
            pct = (current / max(1, total_frames)) * 100
            logger.info(
                "frame_progress",
                video=video_path.name,
                frame=f"{current}/{total_frames}",
                pct=f"{pct:.0f}%",
            )

        result = generate_single_dataset(
            video_path,
            output_dir=output_dir,
            templates_dir=templates_dir,
            progress_callback=_progress,
        )
        results.append(result)

    # Summary.
    succeeded = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    total_frames = sum(r.frame_count for r in results)
    total_reps = sum(r.rep_count for r in results)
    total_time = sum(r.processing_time for r in results)

    logger.info(
        "dataset_generation_complete",
        videos_processed=len(results),
        succeeded=succeeded,
        failed=failed,
        total_frames=total_frames,
        total_reps=total_reps,
        total_time_s=f"{total_time:.2f}",
    )

    return results
