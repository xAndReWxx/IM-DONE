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

from typing import Dict, List
from app.models.packets import ExerciseCard


# ── The catalog. Keys are the stable exercise IDs. ──
EXERCISES: Dict[str, ExerciseCard] = {
    "chin_tuck": ExerciseCard(
        id="chin_tuck",
        name_ar="شد الذقن",
        name_en="Chin Tuck",
        reps=10,
        duration_s=60,
        instructions_ar=[
            "اجلس أو قف بظهر مستقيم.",
            "اسحب ذقنك للخلف ببطء، كأنك ترسم ذقنًا مزدوجًا.",
            "ثبّت لمدة ٣ ثوانٍ، ثم استرخِ.",
            "كرّر التمرين بهدوء وبدون توتر.",
        ],
    ),
    "wall_angel": ExerciseCard(
        id="wall_angel",
        name_ar="ملاك الحائط",
        name_en="Wall Angel",
        reps=10,
        duration_s=90,
        instructions_ar=[
            "قف وظهرك ملاصق للحائط.",
            "ارفع ذراعيك على شكل حرف W ثم Y.",
            "حافظ على ملامسة ظهرك ومرفقيك للحائط.",
            "حرّك الذراعين ببطء، ثم عُد إلى الوضع الأول.",
        ],
    ),
    "thoracic_extension": ExerciseCard(
        id="thoracic_extension",
        name_ar="تمديد الظهر العلوي",
        name_en="Thoracic Extension",
        reps=8,
        duration_s=60,
        instructions_ar=[
            "اجلس على كرسي مع وضع يديك خلف رأسك.",
            "افرد ظهرك للخلف برفق، ولا تجبر الحركة.",
            "اشعر بفتح الصدر ومدّ الجزء العلوي من الظهر.",
            "ثبّت لمدة ٣ ثوانٍ، ثم استرخِ.",
        ],
    ),
    "shoulder_release": ExerciseCard(
        id="shoulder_release",
        name_ar="تحرير الكتف",
        name_en="Shoulder Release",
        reps=10,
        duration_s=75,
        instructions_ar=[
            "قف بظهر مستقيم وذراعيك على جانبيك.",
            "ارفع ذراعيك جانبياً حتى مستوى الكتف.",
            "ثبّت لمدة ٣ ثوانٍ مع التنفس العميق.",
            "أنزل ذراعيك ببطء إلى الوضع الأصلي.",
        ],
    ),
}


# ── Mapping: posture issue → list of exercise IDs to recommend ──
# The first ID is the primary recommendation. Use stable issue keys
# that match what the PostureAnalyzer emits.
ISSUE_TO_EXERCISES: Dict[str, List[str]] = {
    "forward_head": ["chin_tuck", "wall_angel"],
    "rounded_shoulders": ["shoulder_release", "wall_angel", "thoracic_extension"],
    "slouching": ["thoracic_extension", "wall_angel", "shoulder_release"],
}


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
