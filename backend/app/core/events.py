"""
============================================================
PhysioAI Pro V2 - Application Lifespan Events
============================================================
PURPOSE
    Runs once at server start and once at shutdown. We use this
    to:
      • Log the active configuration (super useful when deployed)
      • Eagerly initialize the AI engine (warm the MediaPipe
        model so the first user doesn't pay a cold-start tax)
      • Start the DatasetManager background scan (generates
        exercise datasets from exercise_videos/*.mp4)
      • Gracefully close all active WebSockets on shutdown
============================================================
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code before `yield` runs at startup; after it, at shutdown.
    """
    # ── STARTUP ──
    logger.info(
        "server_starting",
        app_name=settings.app_name,
        version=settings.app_version,
        env=settings.app_env,
        host=settings.host,
        port=settings.port,
        debug=settings.debug,
    )
    logger.info(
        "websocket_config",
        max_connections=settings.ws_max_connections,
        heartbeat_interval=settings.ws_heartbeat_interval,
    )
    logger.info(
        "frame_processing_config",
        max_fps=settings.max_fps,
        target_fps=settings.target_fps,
        max_frame_size=settings.max_frame_size_bytes,
    )
    logger.info("cors_config", allowed_origins=settings.cors_origins_list)

    # Eagerly initialize the AI engine.
    try:
        from app.services.ai_engine import ai_engine
        await ai_engine.initialize()
    except Exception as e:
        logger.error("ai_engine_init_failed", error=str(e))

    # Start dataset generation in the background (non-blocking).
    # It runs in asyncio.to_thread inside scan_and_generate(), so
    # it won't delay server readiness.
    try:
        from app.services.dataset_manager import dataset_manager
        asyncio.create_task(dataset_manager.scan_and_generate())
        logger.info("dataset_scan_scheduled")
    except Exception as e:
        logger.warning("dataset_scan_failed_to_schedule", error=str(e))

    logger.info("server_ready", status="accepting connections")

    yield  # ── application runs ──

    # ── SHUTDOWN ──
    logger.info("server_shutting_down")

    from app.websocket.manager import connection_manager
    await connection_manager.disconnect_all()

    try:
        from app.services.ai_engine import ai_engine
        await ai_engine.cleanup()
    except Exception:
        pass

    logger.info("server_stopped")
