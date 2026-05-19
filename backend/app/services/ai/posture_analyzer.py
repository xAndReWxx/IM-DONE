"""
============================================================
PhysioAI Pro V2 - Posture Analyzer
============================================================
PURPOSE
    Translate a frame's 33 MediaPipe landmarks into:
      • A posture quality score (0-100)
      • A list of detected issue keys (e.g. "forward_head")
      • An Arabic coaching feedback line (single sentence, TTS-ready)

THRESHOLDS — WHERE DO THE NUMBERS COME FROM?
    The numeric cutoffs are loaded from the reference JSON that
    was generated from the project's training datasets:

        dataset_all_points.csv:
            • 2,700 labeled landmark snapshots
            • The "rest" class (n=406) gives us the baseline
              good-posture pose
            • Mean forward-head angle ≈ 18°  (so >22° = warn, >30° = bad)
            • Mean shoulder tilt   ≈ 1.2° (so >5°  = warn, >10° = bad)
            • Mean spine lean      ≈ 1.4° (so >6°  = warn, >12° = bad)

        data.csv:
            • 45,000 rows of angle-y / angle-z / EMG with English
              recommendations per posture class
            • Used to map issue keys to user-facing text in Arabic

CHANGE 6 additions:
    • Moving average buffer (5 frames) per angle to reduce jitter.
    • State persistence: a posture issue is only reported if it
      appears in 3+ consecutive frames (prevents single-frame flips).
============================================================
"""

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Dict, List, Optional

import numpy as np

from app.config import settings
from app.services.ai.geometry import (
    vertical_angle,
    horizontal_tilt,
    midpoint,
)
from app.services.ai.mobility_classifier import MobilityClassifier
from app.utils.logger import get_logger


logger = get_logger(__name__)


# ── MediaPipe landmark indices we actually use ──
LM_NOSE = 0
LM_LEFT_EAR = 7
LM_RIGHT_EAR = 8
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24

# Minimum consecutive frames an issue must persist before it's reported.
_ISSUE_CONFIRM_FRAMES = 3
# Angle moving-average window.
_ANGLE_BUFFER_LEN = 5


@dataclass
class PostureResult:
    """Output of one analysis pass."""
    score: int
    issues: List[str]
    feedback_ar: str
    forward_head_deg: float
    shoulder_tilt_deg: float
    spine_lean_deg: float
    mobility_issues: List[Dict] = field(default_factory=list)


# ── Arabic feedback lines, indexed by issue key ──
ISSUE_FEEDBACK_AR = {
    "forward_head":      "اسحب ذقنك قليلًا للخلف وارفع رأسك",
    "rounded_shoulders": "اسحب كتفيك للخلف وافتح صدرك",
    "slouching":         "اعتدل في جلستك وحافظ على استقامة ظهرك",
    "restricted_arm_mobility": "تمديد ذراعك محدود. تمارين الإطالة قد تساعد.",
    "uneven_shoulders":  "كتفاك غير متوازنين، حاول إرخاء الجانب المرتفع",
}

GOOD_POSTURE_AR = "وضعيتك ممتازة، استمر هكذا"


class _IssueTracker:
    """
    Counts consecutive-frame appearances of each issue key.
    An issue is only emitted once it has been seen for
    _ISSUE_CONFIRM_FRAMES frames in a row.
    """

    def __init__(self) -> None:
        self._counts: Dict[str, int] = {}

    def update(self, raw_issues: List[str]) -> List[str]:
        """
        Feed this frame's raw issue list. Returns the confirmed
        issues (those that have persisted long enough).
        """
        # Increment counts for issues present; reset those absent.
        all_keys = set(self._counts) | set(raw_issues)
        for key in all_keys:
            if key in raw_issues:
                self._counts[key] = self._counts.get(key, 0) + 1
            else:
                self._counts[key] = 0

        return [k for k, v in self._counts.items() if v >= _ISSUE_CONFIRM_FRAMES]


class PostureAnalyzer:
    """
    Stateful analyzer. Each instance holds its own:
      • Per-angle moving average buffers (reduce jitter).
      • Issue persistence tracker (debounce single-frame flips).

    IMPORTANT: one PostureAnalyzer per client. Do NOT share a
    single instance across connections.

    For backwards compatibility the class can still be instantiated
    once and used across clients if the caller does not need per-
    client state — the angle buffers will then mix, which is
    acceptable for a single-user setup (the original V2 design).
    """

    def __init__(self, reference_path: Optional[Path] = None):
        if reference_path is None:
            reference_path = (
                Path(__file__).resolve().parents[2]
                / "reference"
                / "good_posture_reference.json"
            )
        self._reference_path = reference_path
        self._thresholds = self._load_thresholds(reference_path)

        # Per-angle moving average buffers.
        self._angle_bufs: Dict[str, Deque[float]] = {
            "forward_head":    deque(maxlen=_ANGLE_BUFFER_LEN),
            "shoulder_tilt":   deque(maxlen=_ANGLE_BUFFER_LEN),
            "spine_lean":      deque(maxlen=_ANGLE_BUFFER_LEN),
        }
        # Issue persistence debouncer.
        self._issue_tracker = _IssueTracker()
        
        # New mobility classifier
        self._mobility_classifier = MobilityClassifier(fps=15.0)

        logger.info(
            "posture_analyzer_initialized",
            thresholds=self._thresholds,
            source=str(reference_path),
        )

    # ── Public API ──

    def analyze(self, landmarks: np.ndarray) -> PostureResult:
        """
        Run posture analysis on a single smoothed landmark array.

        Args:
            landmarks: shape (33, 4) array of [x, y, z, visibility]

        Returns:
            PostureResult with score, issue keys, and Arabic feedback.
        """
        if landmarks is None or landmarks.shape[0] < 33:
            # No landmarks — reset issue tracker (don't carry over state
            # across gaps where the person left the frame).
            self._issue_tracker = _IssueTracker()
            return PostureResult(
                score=0,
                issues=[],
                feedback_ar="",
                forward_head_deg=0.0,
                shoulder_tilt_deg=0.0,
                spine_lean_deg=0.0,
            )

        # ── Extract 2D points ──
        ear_l  = landmarks[LM_LEFT_EAR][:2]
        ear_r  = landmarks[LM_RIGHT_EAR][:2]
        sh_l   = landmarks[LM_LEFT_SHOULDER][:2]
        sh_r   = landmarks[LM_RIGHT_SHOULDER][:2]
        hip_l  = landmarks[LM_LEFT_HIP][:2]
        hip_r  = landmarks[LM_RIGHT_HIP][:2]

        # ── Raw angle computation ──
        fhp_left  = vertical_angle(ear_l, sh_l)
        fhp_right = vertical_angle(ear_r, sh_r)
        raw_fh    = (fhp_left + fhp_right) / 2.0
        raw_tilt  = horizontal_tilt(sh_l, sh_r)
        sh_mid    = midpoint(sh_l, sh_r)
        hip_mid   = midpoint(hip_l, hip_r)
        raw_lean  = vertical_angle(sh_mid, hip_mid)

        # ── Apply moving average smoothing ──
        self._angle_bufs["forward_head"].append(raw_fh)
        self._angle_bufs["shoulder_tilt"].append(raw_tilt)
        self._angle_bufs["spine_lean"].append(raw_lean)

        forward_head_deg  = float(np.mean(self._angle_bufs["forward_head"]))
        shoulder_tilt_deg = float(np.mean(self._angle_bufs["shoulder_tilt"]))
        spine_lean_deg    = float(np.mean(self._angle_bufs["spine_lean"]))

        # ── Apply thresholds (raw issues for this frame) ──
        raw_issues: List[str] = []
        score = 100
        t = self._thresholds

        if forward_head_deg >= t["forward_head_bad_deg"]:
            raw_issues.append("forward_head")
            score -= 25
        elif forward_head_deg >= t["forward_head_warn_deg"]:
            raw_issues.append("forward_head")
            score -= 12

        if shoulder_tilt_deg >= t["shoulder_tilt_bad_deg"]:
            raw_issues.append("rounded_shoulders")
            score -= 20
        elif shoulder_tilt_deg >= t["shoulder_tilt_warn_deg"]:
            raw_issues.append("rounded_shoulders")
            score -= 8

        if spine_lean_deg >= t["spine_lean_bad_deg"]:
            raw_issues.append("slouching")
            score -= 25
        elif spine_lean_deg >= t["spine_lean_warn_deg"]:
            raw_issues.append("slouching")
            score -= 10

        score = max(0, min(100, score))

        # ── Debounce: only emit issues confirmed for 3+ frames ──
        issues = self._issue_tracker.update(raw_issues)
        # Recalculate score from confirmed issues to stay consistent.
        if len(issues) != len(raw_issues):
            score = 100
        # Update persistent issues
        confirmed_issues = self._issue_tracker.update(raw_issues)
        
        # Process mobility limits (already debounced internally by time window)
        mobility_issues = self._mobility_classifier.process_frame(landmarks)
        for issue in mobility_issues:
            if issue["issue"] not in confirmed_issues:
                confirmed_issues.append(issue["issue"])

        # Decide on coaching feedback.
        # Priority: mobility restrictions > spine lean > forward head > shoulder tilt.
        feedback_ar = GOOD_POSTURE_AR
        if "restricted_arm_mobility" in confirmed_issues:
            feedback_ar = ISSUE_FEEDBACK_AR["restricted_arm_mobility"]
        elif "slouching" in confirmed_issues:
            feedback_ar = ISSUE_FEEDBACK_AR["slouching"]
        elif "forward_head" in confirmed_issues:
            feedback_ar = ISSUE_FEEDBACK_AR["forward_head"]
        elif "rounded_shoulders" in confirmed_issues:
            feedback_ar = ISSUE_FEEDBACK_AR["rounded_shoulders"]
        elif "uneven_shoulders" in confirmed_issues:
            feedback_ar = ISSUE_FEEDBACK_AR["uneven_shoulders"]

        return PostureResult(
            score=score,
            issues=confirmed_issues,
            feedback_ar=feedback_ar,
            forward_head_deg=round(forward_head_deg, 2),
            shoulder_tilt_deg=round(shoulder_tilt_deg, 2),
            spine_lean_deg=round(spine_lean_deg, 2),
            mobility_issues=mobility_issues,
        )

    # ── Threshold loading ──

    def _load_thresholds(self, path: Path) -> dict:
        """
        Load posture thresholds from the reference JSON, falling back
        to defaults in `settings` if anything goes wrong.
        """
        defaults = {
            "forward_head_warn_deg":  settings.fhp_warn_deg,
            "forward_head_bad_deg":   settings.fhp_bad_deg,
            "shoulder_tilt_warn_deg": settings.shoulder_tilt_warn_deg,
            "shoulder_tilt_bad_deg":  settings.shoulder_tilt_bad_deg,
            "spine_lean_warn_deg":    settings.spine_lean_warn_deg,
            "spine_lean_bad_deg":     settings.spine_lean_bad_deg,
        }

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ref = data.get("thresholds", {})
            return {k: float(ref.get(k, defaults[k])) for k in defaults}
        except FileNotFoundError:
            logger.warning("reference_json_missing", path=str(path))
            return defaults
        except Exception as e:
            logger.warning("reference_json_invalid", error=str(e))
            return defaults
