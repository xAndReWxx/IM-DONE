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
from app.services.exercise_engine.feedback_throttler import FeedbackThrottler
from app.services.exercise_engine.realtime_tracker import RealtimeMotionTracker
from app.services.exercise_engine.template_manager import template_manager
from app.utils.logger import get_logger


logger = get_logger(__name__)


try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.warning("opencv_not_installed")


# Phases that count as directional scan data (only front now).
_SCAN_DATA_PHASES = {"front"}

# Exercise correction cooldown seconds (don't spam the user).
_CORRECTION_COOLDOWN = 3.0

# Angle deviation threshold (degrees) before a correction is issued.
_CORRECTION_THRESHOLD = 12.0


# AI processing modes.
AI_MODE_IDLE = "idle"                        # landmarks only, no analysis
AI_MODE_POSTURE_ANALYSIS = "posture_analysis" # calibration + posture scan
AI_MODE_EXERCISE_TRACKING = "exercise_tracking" # exercise validation


class _ClientState:
    """Holds per-client runtime state for the AI pipeline."""

    __slots__ = (
        "filter",
        "analyzer",
        "tracker",
        "motion_tracker",
        "fps_ema",
        "last_frame_time",
        "scan_buffer",
        "last_correction_time",
        "last_correction_text",
        "ai_mode",
        "feedback_throttler",
    )

    def __init__(self) -> None:
        self.filter = LandmarkFilter(alpha=settings.ema_alpha_landmarks)
        self.analyzer = PostureAnalyzer()
        self.tracker: Optional[BaseExerciseTracker] = None
        # AI motion tracker (used when a MotionTemplate is available).
        self.motion_tracker: Optional[RealtimeMotionTracker] = None
        self.fps_ema: float = 0.0
        self.last_frame_time: float = 0.0
        self.scan_buffer: Dict[str, List[List[float]]] = {}
        self.last_correction_time: float = 0.0
        self.last_correction_text: str = ""
        self.ai_mode: str = AI_MODE_IDLE
        self.feedback_throttler = FeedbackThrottler()


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
        # Initialize template manager for AI motion comparison.
        await template_manager.initialize()
        self._initialized = True
        logger.info(
            "ai_engine_ready",
            mediapipe_ready=self._pose_engine.is_ready,
            motion_templates=template_manager.available_exercises,
        )

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
        """Select an exercise and switch to exercise tracking mode."""
        state = self.get_or_create_state(client_id)
        new_tracker = create_tracker(exercise_id)
        if new_tracker is None:
            logger.warning("unknown_exercise_id", exercise_id=exercise_id)
            return False
        state.tracker = new_tracker

        # Try to load an AI motion template for this exercise.
        template = template_manager.get(exercise_id)
        if template:
            state.motion_tracker = RealtimeMotionTracker(template, fps=15.0)
            logger.info("motion_tracker_created", exercise=exercise_id, mode="ai_template")
        else:
            state.motion_tracker = None
            logger.info("motion_tracker_fallback", exercise=exercise_id, mode="rule_based")

        state.ai_mode = AI_MODE_EXERCISE_TRACKING
        state.feedback_throttler.reset()
        logger.info("exercise_selected", client_id=client_id, exercise_id=exercise_id,
                    mode=AI_MODE_EXERCISE_TRACKING)
        return True

    def set_mode(self, client_id: str, mode: str) -> None:
        """Switch AI mode for a client."""
        state = self.get_or_create_state(client_id)
        state.ai_mode = mode
        state.feedback_throttler.reset()
        if mode != AI_MODE_EXERCISE_TRACKING:
            state.tracker = None
            state.motion_tracker = None
        logger.info("ai_mode_changed", client_id=client_id, mode=mode)

    def get_mode(self, client_id: str) -> str:
        """Get the current AI mode for a client."""
        state = self._client_state.get(client_id)
        return state.ai_mode if state else AI_MODE_IDLE

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

    # ── Full-body analysis (Front Only) ──

    async def analyze_360_scan(self, client_id: str) -> dict:
        """
        Run a posture analysis from the captured front snapshot
        and return a ScanResultPacket dict.
        (Kept method name analyze_360_scan for backwards compat with handler)
        """
        state = self._client_state.get(client_id)
        if state is None:
            return ScanResultPacket(
                issues=[],
                recommendations=[],
                analysis_summary="No scan data available.",
            ).model_dump()

        scan_buffer = state.scan_buffer.copy()
        
        # Extract mobility issues that were confidently detected during the continuous scan
        # so they can be included in the final report.
        mobility_issues = state.analyzer._mobility_classifier.process_frame(
            np.zeros((33, 4))  # dummy frame just to get current state if needed, or we just rely on what was returned during the scan
        ) if hasattr(state.analyzer, "_mobility_classifier") else []
        
        # Actually, let's just grab the issues that were confirmed by the issue tracker
        # and any mobility issues stored in the classifier.
        # Wait, the MobilityClassifier evaluates over time. Let's get the latest confident issues from it.
        # We can just look at what the analyzer returned last, or extract directly.
        # A better way is to pass the state.analyzer to _run_front_analysis.
        
        result = await asyncio.to_thread(
            self._run_front_analysis, scan_buffer, state.analyzer
        )
        # Clear the buffer after analysis.
        state.scan_buffer = {}
        return result

    def _run_front_analysis(self, scan_buffer: Dict[str, List[List[float]]], analyzer=None) -> dict:
        """
        CPU-bound front-only analysis. Runs in a thread.

        Strategy:
          - Front view: assess forward head, shoulder level, spine lean
          - Continuous: add any mobility issues detected during the scan
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

        # ── Continuous scan mobility issues ──
        if analyzer is not None and hasattr(analyzer, "_mobility_classifier"):
            # The classifier processes frames continuously. We just need to check if there 
            # are any issues currently confident enough to report.
            # We can re-evaluate the last known state by passing a dummy, or better, 
            # we should have stored them. Actually, the classifier's process_frame evaluates the history.
            # The history is still there. We can just call it with the last frame from the buffer,
            # or just look at the last returned issues from process_frame.
            # Let's just process the front frame again to get the history-based evaluation.
            if front is not None:
                # We need full 33x4, but front is 33x4
                mob_issues = analyzer._mobility_classifier.process_frame(front)
                for m_issue in mob_issues:
                    issue_type = m_issue["issue"]
                    if issue_type not in all_issue_types:
                        all_issue_types.add(issue_type)
                        desc = ""
                        if issue_type == "restricted_arm_mobility":
                            side = m_issue.get("side", "unknown")
                            max_ext = m_issue.get("max_extension", 0.0)
                            desc = f"Restricted arm mobility detected on the {side} side. Maximum extension was limited to {max_ext:.1f}°."
                        elif issue_type == "uneven_shoulders":
                            side = m_issue.get("higher_side", "unknown")
                            desc = f"Persistent shoulder asymmetry detected. The {side} shoulder is higher."
                            
                        issues.append(ScanIssue(
                            type=issue_type,
                            description=desc,
                            severity=m_issue.get("severity", "moderate"),
                        ))

        # ── Build recommendations from detected issues ──
        mapped_issues = [i for i in [
            "forward_head" if "forward_head" in all_issue_types else None,
            "rounded_shoulders" if "shoulder_asymmetry" in all_issue_types else None,
            "slouching" if "spine_lean" in all_issue_types else None,
            "restricted_arm_mobility" if "restricted_arm_mobility" in all_issue_types else None,
            "uneven_shoulders" if "uneven_shoulders" in all_issue_types else None,
        ] if i is not None]

        recommendations = recommend_for_issues(mapped_issues) if mapped_issues else []

        # ── Summary ──
        if not issues:
            summary = "Excellent posture! No significant issues detected."
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

            # Common landmark serialization.
            landmark_dicts = [
                {"x": float(p[0]), "y": float(p[1]), "z": float(p[2]), "visibility": float(p[3])}
                for p in smoothed
            ]

            # ── MODE-DEPENDENT ANALYSIS ──
            posture_score = None
            posture_issues: list = []
            feedback_ar = ""
            recommendations: list = []
            rep_state = None
            exercise_correction: Optional[str] = None

            if state.ai_mode == AI_MODE_POSTURE_ANALYSIS:
                # Full posture analysis (during calibration scan).
                try:
                    posture = state.analyzer.analyze(smoothed)
                    posture_score = posture.score
                    posture_issues = posture.issues
                    feedback_ar = posture.feedback_ar
                    recommendations = recommend_for_issues(posture.issues) if posture.issues else []
                except Exception as e:
                    logger.exception("posture_analysis_failed")
                    posture_score = None
                    posture_issues = []
                    feedback_ar = ""
                    recommendations = []

            elif state.ai_mode == AI_MODE_EXERCISE_TRACKING:
                # Exercise tracking only — no posture analysis.
                if state.motion_tracker is not None:
                    # ── AI Motion Comparison Mode ──
                    tracking_result = state.motion_tracker.process(smoothed)
                    rep_state = {
                        "exercise_id": state.motion_tracker._template.exercise_id,
                        "reps": tracking_result.reps,
                        "phase": tracking_result.phase,
                        "last_feedback_ar": tracking_result.feedback_ar or "استعداد",
                        "quality_score": tracking_result.quality_score,
                        "similarity": tracking_result.similarity,
                    }
                    if tracking_result.correction:
                        exercise_correction = tracking_result.correction
                    feedback_ar = tracking_result.feedback_ar
                elif state.tracker is not None:
                    # ── Fallback: rule-based tracker ──
                    state.tracker.process(smoothed)
                    rep_state = state.tracker.to_rep_state()
                    correction = self._check_exercise_correction(state, smoothed, now)
                    if correction:
                        exercise_correction = correction

            # AI_MODE_IDLE: landmarks only, no analysis.
            if state.ai_mode == AI_MODE_IDLE:
                # Explicitly guarantee we do not drop the packet
                pass
                
            packet = PoseResultPacket(
                fps=round(state.fps_ema, 1),
                landmarks=landmark_dicts,
                posture_score=posture_score,
                posture_issues=posture_issues,
                feedback_ar=feedback_ar,
                recommendations=recommendations,
                rep_state=rep_state,
                exercise_correction=exercise_correction,
            )
            
            logger.debug("pose_packet_sent")
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
        the threshold, respecting cooldowns AND the feedback throttler.
        """
        if state.tracker is None:
            return None

        # Enforce cooldown between corrections.
        if now - state.last_correction_time < _CORRECTION_COOLDOWN:
            return None

        exercise_id: str = getattr(state.tracker, "exercise_id", "")
        correction = self._heuristic_correction(exercise_id, smoothed)

        if correction and correction != state.last_correction_text:
            # Run through the throttler for additional spam prevention.
            allowed = state.feedback_throttler.try_send(correction)
            if allowed:
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

        elif exercise_id == "shoulder_release":
            if tilt > 10:
                return "Keep both shoulders level as you raise your arms — don't tilt."
            if lean > 12:
                return "Stand upright — don't lean forward during the arm raise."
            if fh > 28:
                return "Keep your head aligned over your shoulders — don't push it forward."

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
