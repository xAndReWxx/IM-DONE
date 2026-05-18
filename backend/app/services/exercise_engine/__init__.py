"""
============================================================
PhysioAI Pro V2 - Exercise Engine
============================================================
AI motion comparison engine with:
  - Video processing (MediaPipe Pose)
  - Landmark normalization (hip-center, torso-scale)
  - Joint angle extraction (15+ angles)
  - Automatic phase detection (rest/concentric/peak/eccentric)
  - Motion template generation (canonical rep)
  - DTW-based realtime comparison
  - Feedback throttling
  - Quality scoring (0-100)
  - JSON + NPZ dataset export
============================================================
"""

from app.services.exercise_engine.feedback_throttler import (
    FeedbackThrottler,
    ThrottlerConfig,
)
from app.services.exercise_engine.video_processor import (
    discover_videos,
    process_video,
    VideoMetadata,
    VideoProcessingResult,
)
from app.services.exercise_engine.landmark_normalizer import (
    normalize_landmarks,
    interpolate_missing_frames,
    center_and_scale,
    temporal_smooth,
)
from app.services.exercise_engine.angle_extractor import (
    extract_angles,
    get_primary_angle_names,
)
from app.services.exercise_engine.phase_detector import (
    detect_phases,
    PhaseLabel,
    Phase,
    PhaseSequence,
    get_per_frame_labels,
)
from app.services.exercise_engine.motion_template import (
    MotionTemplate,
    generate_template,
)
from app.services.exercise_engine.dtw_comparator import (
    dtw_distance,
    dtw_similarity,
    multi_angle_dtw_similarity,
    compare_to_template,
    ComparisonResult,
)
from app.services.exercise_engine.realtime_tracker import (
    RealtimeMotionTracker,
    MotionTrackingResult,
)
from app.services.exercise_engine.template_manager import (
    TemplateManager,
    template_manager,
)
from app.services.exercise_engine.dataset_exporter import (
    export_dataset,
    export_compact_npz,
)
from app.services.exercise_engine.dataset_generator import (
    generate_all_datasets,
    generate_single_dataset,
    GenerationResult,
)

from app.services.exercise_engine.dataset_quality_validator import (
    validate_dataset,
    ValidationResult,
    ValidationMetrics,
)
from app.services.exercise_engine.mistake_classifier import (
    classify_mistakes,
)

__all__ = [
    # Feedback
    "FeedbackThrottler",
    "ThrottlerConfig",
    # Video processing
    "discover_videos",
    "process_video",
    "VideoMetadata",
    "VideoProcessingResult",
    # Normalization
    "normalize_landmarks",
    "interpolate_missing_frames",
    "center_and_scale",
    "temporal_smooth",
    # Angles
    "extract_angles",
    "get_primary_angle_names",
    # Phase detection
    "detect_phases",
    "PhaseLabel",
    "Phase",
    "PhaseSequence",
    "get_per_frame_labels",
    # Templates
    "MotionTemplate",
    "generate_template",
    "TemplateManager",
    "template_manager",
    # DTW comparison
    "dtw_distance",
    "dtw_similarity",
    "multi_angle_dtw_similarity",
    "compare_to_template",
    "ComparisonResult",
    "trajectory_similarity",
    # Realtime tracking
    "RealtimeMotionTracker",
    "MotionTrackingResult",
    # Export
    "export_dataset",
    "export_compact_npz",
    # Generator
    "generate_all_datasets",
    "generate_single_dataset",
    "GenerationResult",
    # Validation & Mistakes
    "validate_dataset",
    "ValidationResult",
    "ValidationMetrics",
    "classify_mistakes",
]
