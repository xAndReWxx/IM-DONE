"""
============================================================
PhysioAI Pro V2 - Exercise Trackers Registry
============================================================
PURPOSE
    One place that maps exercise IDs → tracker classes. The
    AI engine looks here to instantiate the right tracker
    when a user selects an exercise via WebSocket.

ADDING A NEW EXERCISE
    1. Create new_exercise.py extending BaseExerciseTracker.
    2. Import it below.
    3. Add it to TRACKER_REGISTRY with a stable ID.
    4. Register the matching ExerciseCard in
       services/ai/exercise_catalog.py.
============================================================
"""

from typing import Dict, Type

from app.services.ai.exercises.base import (
    BaseExerciseTracker,
    ExercisePhase,
    ARABIC_PHASE_FEEDBACK,
)
from app.services.ai.exercises.chin_tuck import ChinTuckTracker
from app.services.ai.exercises.wall_angel import WallAngelTracker
from app.services.ai.exercises.thoracic_extension import ThoracicExtensionTracker


# Stable ID → tracker class. Keys must match exercise_catalog.EXERCISES.
TRACKER_REGISTRY: Dict[str, Type[BaseExerciseTracker]] = {
    "chin_tuck":           ChinTuckTracker,
    "wall_angel":          WallAngelTracker,
    "thoracic_extension":  ThoracicExtensionTracker,
}


def create_tracker(exercise_id: str) -> BaseExerciseTracker | None:
    """Instantiate the tracker for a given exercise ID, or None if unknown."""
    cls = TRACKER_REGISTRY.get(exercise_id)
    return cls() if cls else None


__all__ = [
    "BaseExerciseTracker",
    "ExercisePhase",
    "ARABIC_PHASE_FEEDBACK",
    "ChinTuckTracker",
    "WallAngelTracker",
    "ThoracicExtensionTracker",
    "TRACKER_REGISTRY",
    "create_tracker",
]
