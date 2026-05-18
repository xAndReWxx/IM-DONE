# PhysioAI Pro V2 — AI subpackage
# Computer-vision + posture-analysis pipeline (MediaPipe-backed).

from app.services.ai.pose_engine import PoseEngine
from app.services.ai.posture_analyzer import PostureAnalyzer, PostureResult
from app.services.ai.landmark_filter import LandmarkFilter
from app.services.ai.exercises import TRACKER_REGISTRY, create_tracker
from app.services.ai.exercise_catalog import (
    EXERCISES,
    ISSUE_TO_EXERCISES,
    get_exercise,
    recommend_for_issues,
)

__all__ = [
    "PoseEngine",
    "PostureAnalyzer",
    "PostureResult",
    "LandmarkFilter",
    "TRACKER_REGISTRY",
    "create_tracker",
    "EXERCISES",
    "ISSUE_TO_EXERCISES",
    "get_exercise",
    "recommend_for_issues",
]
