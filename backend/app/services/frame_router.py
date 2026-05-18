"""
============================================================
PhysioAI Pro V2 - Frame Router
============================================================
PURPOSE
    Thin mediator between the WebSocket handler and the AI engine.
    Adds:
      • Per-client rate limiting (caps processing at MAX_FPS so a
        single hyperactive client can't monopolize the CPU)
      • Global concurrency limit (semaphore — keeps overall load
        sane when many clients connect simultaneously)
      • A graceful "skipped" response when a frame is dropped,
        so the client knows the WS is healthy

WHY A SEPARATE ROUTER (NOT JUST CALL THE ENGINE)?
    Rate limiting and concurrency control are orthogonal to AI
    logic; putting them in a thin layer keeps the engine focused
    on the AI pipeline itself. It also makes it trivial to add
    pre-processing (resize, crop) or post-processing (cross-frame
    smoothing) later without touching engine code.
============================================================
"""

import asyncio
import time
from typing import Dict

from app.config import settings
from app.core.exceptions import AIEngineError
from app.models.packets import FramePacket
from app.services.ai_engine import ai_engine
from app.utils.logger import get_logger


logger = get_logger(__name__)


class FrameRouter:
    """
    Routes camera frames to the AI engine with rate limiting and
    concurrency caps.
    """

    def __init__(self) -> None:
        # Last "processed" wall-clock time per client (monotonic).
        self._last_frame_time: Dict[str, float] = {}

        # Limit concurrent AI calls. Tune based on hardware:
        #  • CPU only:  ~ #physical cores
        #  • One GPU:   raise this only if you've sharded the model
        self._processing_semaphore = asyncio.Semaphore(8)

        # Per-client drop counter for monitoring.
        self._frames_dropped: Dict[str, int] = {}

    async def process_frame(self, frame_packet: FramePacket, client_id: str) -> dict:
        """
        Process or skip a single frame.

        Returns a dict matching PoseResultPacket — including a
        "skipped"-style payload if the frame was rate-limited.
        """
        # ── Step 1: Rate limit ──
        if not self._check_rate_limit(client_id):
            self._frames_dropped[client_id] = self._frames_dropped.get(client_id, 0) + 1
            logger.debug(
                "frame_dropped_rate_limit",
                client_id=client_id,
                dropped_total=self._frames_dropped[client_id],
            )
            return self._skipped_result()

        # ── Step 2: Concurrency cap with timeout ──
        try:
            async with asyncio.timeout(2.0):
                async with self._processing_semaphore:
                    return await self._route_to_engine(frame_packet, client_id)
        except asyncio.TimeoutError:
            logger.warning("processing_timeout", client_id=client_id)
            return self._skipped_result(message="Server busy, retrying...")

    async def _route_to_engine(self, frame_packet: FramePacket, client_id: str) -> dict:
        """Send the frame to the engine and bubble engine errors up."""
        try:
            return await ai_engine.process_frame(frame_packet.frame, client_id)
        except AIEngineError:
            raise
        except Exception as e:
            logger.error(
                "ai_engine_processing_error",
                client_id=client_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise AIEngineError(f"Failed to process frame: {e}", original_error=e)

    def _check_rate_limit(self, client_id: str) -> bool:
        """True if we should process this frame; False if we should drop it."""
        now = time.monotonic()
        min_interval = 1.0 / max(settings.max_fps, 1)
        last = self._last_frame_time.get(client_id, 0.0)
        if now - last < min_interval:
            return False
        self._last_frame_time[client_id] = now
        return True

    def _skipped_result(self, message: str = "") -> dict:
        """Stand-in payload for dropped/skipped frames."""
        return {
            "type": "pose_result",
            "fps": settings.target_fps,
            "landmarks": None,
            "posture_score": None,
            "posture_issues": [],
            "feedback_ar": message,
            "recommendations": [],
            "rep_state": None,
            "latency_ms": 0,
            "skipped": True,
        }

    def cleanup_client(self, client_id: str) -> None:
        """Drop per-client bookkeeping when they disconnect."""
        self._last_frame_time.pop(client_id, None)
        self._frames_dropped.pop(client_id, None)


# ── Singleton ──
frame_router = FrameRouter()
