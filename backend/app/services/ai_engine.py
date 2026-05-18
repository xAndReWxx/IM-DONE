"""
============================================================
PhysioAI Pro V2 - AI Engine (Main Orchestrator)
============================================================
PURPOSE
    Single entry point that turns a raw JPEG frame into a fully
    populated PoseResultPacket. Stitches together:

        JPEG bytes
          → OpenCV decode
          → MediaPipe pose detection
          → EMA smoothing
          → Posture analysis (score, issues, Arabic feedback)
          → Exercise recommendations
          → Exercise rep tracking (FSM)
          → Exercise form correction (dataset comparison)
          → PoseResultPacket dict

PER-CONNECTION STATE
    Each client has its own smoothing filter, rep tracker, scan
    buffer, and correction cooldown, stored in `_client_state`.

CHANGES
    • scan_buffer: per-client dict of phase → landmarks for 360° scan
    • analyze_360_scan: full-body analysis from 4 directions
    • Exercise correction: compare live angles to dataset frame,
      emit correction instruction if deviation > threshold
============================================================
"""

import asyncio
import base64
import time
from typing import Dict, List, Optional

import numpy as np

from app.config import settings
from app.core.exceptions import AIEngineError
from app.models.packets import (
    PoseResultPacket,
    ScanResultPacket,
    ScanIssue,
)
from app.services.ai import (
    PoseEngine,
    PostureAnalyzer,
    LandmarkFilter,
    create_tracker,
    recommend_for_issues,
)
from app.services.ai.exercises.base import BaseExerciseTracker
from app.utils.logger import get_logger


logger = get_logger(__name__)


try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.warning("opencv_not_installed")


# Phases that count as directional scan data (neutral is warm-up only).
_SCAN_DATA_PHASES = {"front", "right", "left", "back"}

# Exercise correction cooldown seconds (don't spam the user).
_CORRECTION_COOLDOWN = 3.0

# Angle deviation threshold (degrees) before a correction is issued.
_CORRECTION_THRESHOLD = 12.0


class _ClientState:
    """Holds per-client runtime state for the AI pipeline."""

    __slots__ = (
        "filter",
        "analyzer",
        "tracker",
        "fps_ema",
        "last_frame_time",
        "scan_buffer",
        "last_correction_time",
        "last_correction_text",
    )

    def __init__(self) -> None:
        self.filter = LandmarkFilter(alpha=settings.ema_alpha_landmarks)
        # Per-client PostureAnalyzer so the debounce/smoothing state
        # is isolated (not shared across connections).
        self.analyzer = PostureAnalyzer()
        self.tracker: Optional[BaseExerciseTracker] = None
        self.fps_ema: float = 0.0
        self.last_frame_time: float = 0.0
        # scan_buffer: {phase_name: list of [x,y,z,v] rows}
        self.scan_buffer: Dict[str, List[List[float]]] = {}
        self.last_correction_time: float = 0.0
        self.last_correction_text: str = ""


class AIEngine:
    """
    Realtime physiotherapy pipeline.

    Public methods are async to integrate cleanly with the WS handler.
    """

    def __init__(self) -> None:
        self._pose_engine = PoseEngine()
        self._shared_analyzer = PostureAnalyzer()   # kept for backwards compat
        self._client_state: Dict[str, _ClientState] = {}
        self._initialized = False

    @property
    def is_ready(self) -> bool:
        return self._initialized and self._pose_engine.is_ready

    # ── Lifecycle ──

    async def initialize(self) -> None:
        if self._initialized:
            return
        if not OPENCV_AVAILABLE:
            logger.warning("ai_engine_init_no_opencv")
        await asyncio.to_thread(self._pose_engine.initialize)
        self._initialized = True
        logger.info("ai_engine_ready", mediapipe_ready=self._pose_engine.is_ready)

    async def cleanup(self) -> None:
        self._pose_engine.close()
        self._client_state.clear()
        self._initialized = False

    # ── Per-client control ──

    def get_or_create_state(self, client_id: str) -> _ClientState:
        state = self._client_state.get(client_id)
        if state is None:
            state = _ClientState()
            self._client_state[client_id] = state
        return state

    def select_exercise(self, client_id: str, exercise_id: str) -> bool:
        state = self.get_or_create_state(client_id)
        new_tracker = create_tracker(exercise_id)
        if new_tracker is None:
            logger.warning("unknown_exercise_id", exercise_id=exercise_id)
            return False
        state.tracker = new_tracker
        logger.info("exercise_selected", client_id=client_id, exercise_id=exercise_id)
        return True

    def reset_reps(self, client_id: str) -> None:
        state = self._client_state.get(client_id)
        if state and state.tracker:
            state.tracker.reset()

    def cleanup_client(self, client_id: str) -> None:
        self._client_state.pop(client_id, None)

    # ── Scan buffer management ──

    def reset_scan_buffer(self, client_id: str) -> None:
        """Clear accumulated scan data for this client."""
        state = self.get_or_create_state(client_id)
        state.scan_buffer = {}

    def store_scan_phase(
        self,
        client_id: str,
        phase: str,
        landmarks: List[List[float]],
    ) -> None:
        """Store one phase's landmark snapshot."""
        state = self.get_or_create_state(client_id)
        state.scan_buffer[phase] = landmarks

    def scan_buffer_complete(self, client_id: str) -> bool:
        """True once all four directional phases have been received."""
        state = self._client_state.get(client_id)
        if state is None:
            return False
        return _SCAN_DATA_PHASES.issubset(state.scan_buffer.keys())

    # ── 360° Full-body analysis ──

    async def analyze_360_scan(self, client_id: str) -> dict:
        """
        Run a comprehensive posture analysis from the four captured
        direction snapshots and return a ScanResultPacket dict.
        """
        state = self._client_state.get(client_id)
        if state is None:
            return ScanResultPacket(
                issues=[],
                recommendations=[],
                analysis_summary="No scan data available.",
            ).model_dump()

        scan_buffer = state.scan_buffer.copy()
        result = await asyncio.to_thread(
            self._run_360_analysis, scan_buffer
        )
        # Clear the buffer after analysis.
        state.scan_buffer = {}
        return result

    def _run_360_analysis(self, scan_buffer: Dict[str, List[List[float]]]) -> dict:
        """
        CPU-bound 360° analysis. Runs in a thread.

        Strategy:
          - Front view: assess forward head, shoulder level, spine lean
          - Side views (right/left): assess forward head depth, kyphosis
          - Back view: assess shoulder symmetry, lateral lean

        Since we only have 2D MediaPipe landmarks, we approximate
        depth cues from the relative positions available in each view.
        """
        issues: List[ScanIssue] = []
        all_issue_types: set = set()

        def _to_array(raw: List[List[float]]) -> Optional[np.ndarray]:
            if not raw or len(raw) < 33:
                return None
            try:
                return np.array(raw, dtype=float)
            except Exception:
                return None

        # ── Front view analysis ──
        front = _to_array(scan_buffer.get("front", []))
        if front is not None:
            from app.services.ai.geometry import vertical_angle, horizontal_tilt, midpoint
            LM_LEFT_EAR, LM_RIGHT_EAR = 7, 8
            LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER = 11, 12
            LM_LEFT_HIP, LM_RIGHT_HIP = 23, 24

            ear_l  = front[LM_LEFT_EAR][:2]
            ear_r  = front[LM_RIGHT_EAR][:2]
            sh_l   = front[LM_LEFT_SHOULDER][:2]
            sh_r   = front[LM_RIGHT_SHOULDER][:2]
            hip_l  = front[LM_LEFT_HIP][:2]
            hip_r  = front[LM_RIGHT_HIP][:2]

            fh = (vertical_angle(ear_l, sh_l) + vertical_angle(ear_r, sh_r)) / 2.0
            tilt = horizontal_tilt(sh_l, sh_r)
            lean = vertical_angle(midpoint(sh_l, sh_r), midpoint(hip_l, hip_r))

            if fh > 30 and "forward_head" not in all_issue_types:
                all_issue_types.add("forward_head")
                issues.append(ScanIssue(
                    type="forward_head",
                    description=f"Forward head posture detected (angle {fh:.1f}°). The head is positioned too far in front of the shoulders.",
                    severity="severe" if fh > 40 else "moderate",
                ))
            elif fh > 22 and "forward_head" not in all_issue_types:
                all_issue_types.add("forward_head")
                issues.append(ScanIssue(
                    type="forward_head",
                    description=f"Mild forward head tendency ({fh:.1f}°). Chin tuck exercises recommended.",
                    severity="mild",
                ))

            if tilt > 10 and "shoulder_asymmetry" not in all_issue_types:
                all_issue_types.add("shoulder_asymmetry")
                issues.append(ScanIssue(
                    type="shoulder_asymmetry",
                    description=f"Shoulder height asymmetry detected ({tilt:.1f}°). One shoulder is noticeably lower than the other.",
                    severity="moderate" if tilt > 15 else "mild",
                ))

            if lean > 12 and "spine_lean" not in all_issue_types:
                all_issue_types.add("spine_lean")
                issues.append(ScanIssue(
                    type="spine_lean",
                    description=f"Spinal lean detected ({lean:.1f}°). Upper body is not vertical.",
                    severity="severe" if lean > 20 else "moderate",
                ))

        # ── Side view analysis (use the average of left and right if available) ──
        right_arr = _to_array(scan_buffer.get("right", []))
        left_arr  = _to_array(scan_buffer.get("left", []))

        for side_arr in filter(lambda a: a is not None, [right_arr, left_arr]):
            from app.services.ai.geometry import vertical_angle
            LM_LEFT_EAR, LM_LEFT_SHOULDER, LM_LEFT_HIP = 7, 11, 23
            LM_RIGHT_EAR, LM_RIGHT_SHOULDER, LM_RIGHT_HIP = 8, 12, 24
            # Use whichever side is more visible (higher visibility).
            if side_arr[LM_LEFT_SHOULDER][3] >= side_arr[LM_RIGHT_SHOULDER][3]:
                ear, sh, hip = side_arr[LM_LEFT_EAR][:2], side_arr[LM_LEFT_SHOULDER][:2], side_arr[LM_LEFT_HIP][:2]
            else:
                ear, sh, hip = side_arr[LM_RIGHT_EAR][:2], side_arr[LM_RIGHT_SHOULDER][:2], side_arr[LM_RIGHT_HIP][:2]

            side_fh = vertical_angle(ear, sh)
            if side_fh > 35 and "kyphosis_risk" not in all_issue_types:
                all_issue_types.add("kyphosis_risk")
                issues.append(ScanIssue(
                    type="kyphosis_risk",
                    description=f"Possible thoracic kyphosis visible from the side ({side_fh:.1f}° head forward). Thoracic extension exercises recommended.",
                    severity="moderate",
                ))
            break  # Analyze only once (first valid side view)

        # ── Back view analysis ──
        back = _to_array(scan_buffer.get("back", []))
        if back is not None:
            from app.services.ai.geometry import horizontal_tilt
            LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER = 11, 12
            LM_LEFT_HIP, LM_RIGHT_HIP = 23, 24
            sh_tilt  = horizontal_tilt(back[LM_LEFT_SHOULDER][:2], back[LM_RIGHT_SHOULDER][:2])
            hip_tilt = horizontal_tilt(back[LM_LEFT_HIP][:2], back[LM_RIGHT_HIP][:2])
            if abs(sh_tilt - hip_tilt) > 8 and "pelvic_tilt" not in all_issue_types:
                all_issue_types.add("pelvic_tilt")
                issues.append(ScanIssue(
                    type="pelvic_tilt",
                    description="Possible pelvic tilt detected from the back view. Hip and shoulder lines are not parallel.",
                    severity="mild",
                ))

        # ── Build recommendations from detected issues ──
        mapped_issues = [i for i in [
            "forward_head" if "forward_head" in all_issue_types else None,
            "rounded_shoulders" if "kyphosis_risk" in all_issue_types else None,
            "slouching" if "spine_lean" in all_issue_types else None,
        ] if i is not None]

        recommendations = recommend_for_issues(mapped_issues) if mapped_issues else []

        # ── Summary ──
        if not issues:
            summary = "Excellent posture! No significant issues detected across all 4 scan directions."
        else:
            count = len(issues)
            severity_counts = {"severe": 0, "moderate": 0, "mild": 0}
            for iss in issues:
                severity_counts[iss.severity] = severity_counts.get(iss.severity, 0) + 1
            summary = (
                f"{count} issue{'s' if count > 1 else ''} detected. "
                + (f"{severity_counts['severe']} severe, " if severity_counts["severe"] else "")
                + (f"{severity_counts['moderate']} moderate, " if severity_counts["moderate"] else "")
                + (f"{severity_counts['mild']} mild." if severity_counts["mild"] else "")
            ).strip(", ") + " See recommendations below."

        return ScanResultPacket(
            issues=issues,
            recommendations=recommendations,
            analysis_summary=summary,
        ).model_dump()

    # ── Main per-frame entry point ──

    async def process_frame(self, frame_data_b64: str, client_id: str) -> dict:
        """
        Decode → infer → analyze → rep-track → correction check.
        Returns a dict ready to be serialized into a pose_result message.
        """
        if not self._initialized:
            await self.initialize()

        state = self.get_or_create_state(client_id)

        # ── Update FPS estimate ──
        now = time.monotonic()
        if state.last_frame_time > 0:
            inst_fps = 1.0 / max(now - state.last_frame_time, 1e-3)
            state.fps_ema = (
                inst_fps if state.fps_ema == 0.0
                else 0.2 * inst_fps + 0.8 * state.fps_ema
            )
        state.last_frame_time = now

        if not OPENCV_AVAILABLE:
            return self._empty_result(state).model_dump()

        try:
            # ── Decode JPEG ──
            try:
                img_bytes = base64.b64decode(frame_data_b64, validate=False)
                np_arr = np.frombuffer(img_bytes, dtype=np.uint8)
                bgr_frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if bgr_frame is None:
                    return self._empty_result(state).model_dump()
                rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
            except Exception as e:
                raise AIEngineError(f"Frame decode failed: {e}", original_error=e)

            # ── Pose inference ──
            raw_landmarks = await asyncio.to_thread(
                self._pose_engine.detect, rgb_frame
            )

            if raw_landmarks is None or raw_landmarks.shape[0] < 33:
                state.filter.reset()
                return self._empty_result(state).model_dump()

            # ── Smooth landmarks ──
            smoothed = state.filter.filter(raw_landmarks)

            # ── Posture analysis (per-client instance for proper debouncing) ──
            posture = state.analyzer.analyze(smoothed)

            # ── Recommendations ──
            recommendations = recommend_for_issues(posture.issues) if posture.issues else []

            # ── Exercise tracking ──
            rep_state = None
            if state.tracker is not None:
                state.tracker.process(smoothed)
                rep_state = state.tracker.to_rep_state()

            # ── Exercise correction check ──
            exercise_correction: Optional[str] = None
            if state.tracker is not None:
                correction = self._check_exercise_correction(state, smoothed, now)
                if correction:
                    exercise_correction = correction

            # ── Build response packet ──
            packet = PoseResultPacket(
                fps=round(state.fps_ema, 1),
                landmarks=[
                    {"x": float(p[0]), "y": float(p[1]), "z": float(p[2]), "visibility": float(p[3])}
                    for p in smoothed
                ],
                posture_score=posture.score,
                posture_issues=posture.issues,
                feedback_ar=posture.feedback_ar,
                recommendations=recommendations,
                rep_state=rep_state,
                exercise_correction=exercise_correction,
            )
            return packet.model_dump()

        except AIEngineError:
            raise
        except Exception as e:
            logger.error(
                "ai_engine_unexpected_error",
                client_id=client_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise AIEngineError(f"Pipeline failed: {e}", original_error=e)

    # ── Exercise correction helpers ──

    def _check_exercise_correction(
        self,
        state: _ClientState,
        smoothed: np.ndarray,
        now: float,
    ) -> Optional[str]:
        """
        Compare the current pose to the active exercise's ideal form.
        Returns an English correction instruction if deviation exceeds
        the threshold and the cooldown has elapsed.

        Without a loaded exercise dataset we use heuristic checks
        based on the exercise type (tracker class name).
        """
        if state.tracker is None:
            return None

        # Enforce cooldown between corrections.
        if now - state.last_correction_time < _CORRECTION_COOLDOWN:
            return None

        exercise_id: str = getattr(state.tracker, "exercise_id", "")
        correction = self._heuristic_correction(exercise_id, smoothed)

        if correction and correction != state.last_correction_text:
            state.last_correction_time = now
            state.last_correction_text = correction
            return correction

        return None

    def _heuristic_correction(
        self,
        exercise_id: str,
        landmarks: np.ndarray,
    ) -> Optional[str]:
        """
        Rule-based form correction for each exercise.
        Returns None if the form looks acceptable.
        """
        try:
            from app.services.ai.geometry import vertical_angle, horizontal_tilt, midpoint
        except Exception:
            return None

        LM_LEFT_EAR, LM_RIGHT_EAR = 7, 8
        LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER = 11, 12
        LM_LEFT_HIP, LM_RIGHT_HIP = 23, 24

        sh_l  = landmarks[LM_LEFT_SHOULDER][:2]
        sh_r  = landmarks[LM_RIGHT_SHOULDER][:2]
        ear_l = landmarks[LM_LEFT_EAR][:2]
        ear_r = landmarks[LM_RIGHT_EAR][:2]
        hip_l = landmarks[LM_LEFT_HIP][:2]
        hip_r = landmarks[LM_RIGHT_HIP][:2]

        fh   = (vertical_angle(ear_l, sh_l) + vertical_angle(ear_r, sh_r)) / 2.0
        tilt = horizontal_tilt(sh_l, sh_r)
        lean = vertical_angle(midpoint(sh_l, sh_r), midpoint(hip_l, hip_r))

        if exercise_id == "chin_tuck":
            if fh > 28:
                return "Tuck your chin further back — keep your ears directly over your shoulders."
            if lean > 15:
                return "Keep your spine upright while tucking your chin — don't lean forward."

        elif exercise_id == "wall_angel":
            if tilt > 10:
                return "Keep both shoulders level against the wall — don't let one drop."
            if lean > 12:
                return "Press your lower back against the wall and keep your torso vertical."

        elif exercise_id == "thoracic_extension":
            if lean < 5:
                return "Extend your upper back further — open your chest toward the ceiling."
            if fh > 30:
                return "Keep your head neutral as you extend — don't jut your chin forward."

        return None

    # ── Helpers ──

    def _empty_result(self, state: _ClientState) -> PoseResultPacket:
        return PoseResultPacket(
            fps=round(state.fps_ema, 1),
            landmarks=None,
            posture_score=None,
            posture_issues=[],
            feedback_ar="",
            recommendations=[],
            rep_state=state.tracker.to_rep_state() if state.tracker else None,
            exercise_correction=None,
        )


# ── Singleton ──
ai_engine = AIEngine()
