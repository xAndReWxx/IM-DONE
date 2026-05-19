"""
============================================================
PhysioAI Pro V2 - Exercise Catalog
============================================================
PURPOSE
    Static catalog of exercises the AI can recommend. Each entry
    has English + Arabic display content, step-by-step Arabic
    instructions for the UI, and a mapping from posture issue
    → recommended exercises.

WHY HARDCODED?
    Three exercises is a small, well-curated set for the MVP.
    Externalizing to a DB or JSON file is easy later (just swap
    EXERCISES for a loader function); for now, inline is faster
    and easier to review.

ADDING A NEW EXERCISE
    1. Add an entry to EXERCISES.
    2. Add it to the relevant lists in ISSUE_TO_EXERCISES.
    3. Create a tracker class in services/ai/exercises/ and
       register it in services/ai/exercises/__init__.py.
============================================================
"""

import json
from pathlib import Path
from typing import Dict, List
from app.models.packets import ExerciseCard
from app.utils.logger import get_logger

logger = get_logger(__name__)

EXERCISES: Dict[str, ExerciseCard] = {}
ISSUE_TO_EXERCISES: Dict[str, List[str]] = {}

def _load_catalog():
    """
    Dynamically discover and load exercises from the generated JSON datasets.
    """
    global EXERCISES, ISSUE_TO_EXERCISES
    EXERCISES.clear()
    ISSUE_TO_EXERCISES.clear()

    # Find datasets dir
    backend_root = Path(__file__).resolve().parent.parent.parent.parent
    datasets_dir = backend_root / "exercise_datasets"
    
    if not datasets_dir.exists():
        logger.warning("no_exercise_datasets_dir_found")
        return

    for json_path in datasets_dir.glob("*.json"):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            ex_id = data.get("exercise")
            meta = data.get("metadata", {})
            
            if not ex_id or not meta:
                continue
                
            # Create Card
            card = ExerciseCard(
                id=ex_id,
                name_en=meta.get("name_en", ex_id.replace("_", " ").title()),
                name_ar=meta.get("name_ar", ex_id.replace("_", " ").title()),
                reps=meta.get("reps", 10),
                duration_s=meta.get("duration_s", 60),
                instructions_ar=meta.get("instructions_ar", []),
            )
            EXERCISES[ex_id] = card
            
            # Map target issues
            issues = meta.get("target_posture_issue", [])
            for issue in issues:
                if issue not in ISSUE_TO_EXERCISES:
                    ISSUE_TO_EXERCISES[issue] = []
                ISSUE_TO_EXERCISES[issue].append(ex_id)
                
        except Exception as e:
            logger.error("failed_to_load_exercise_dataset", file=json_path.name, error=str(e))
            
    logger.info("exercise_catalog_loaded", count=len(EXERCISES))

# Load immediately on module import
_load_catalog()


def get_exercise(exercise_id: str) -> ExerciseCard | None:
    """Look up an exercise card by ID."""
    return EXERCISES.get(exercise_id)


def recommend_for_issues(issues: List[str], limit: int = 3) -> List[ExerciseCard]:
    """
    Build a recommendation list from a set of detected posture issues.

    Preserves issue priority and deduplicates so the same exercise
    isn't suggested twice if it covers multiple issues.
    """
    seen: set[str] = set()
    out: List[ExerciseCard] = []
    for issue in issues:
        for ex_id in ISSUE_TO_EXERCISES.get(issue, []):
            if ex_id in seen:
                continue
            card = EXERCISES.get(ex_id)
            if not card:
                continue
            seen.add(ex_id)
            out.append(card)
            if len(out) >= limit:
                return out
    return out
