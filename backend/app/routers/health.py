"""
============================================================
PhysioAI Pro V2 - Health Check Routes
============================================================
PURPOSE
    Standard HTTP endpoints for monitoring and quick "is it
    alive?" sanity checks during development.

ENDPOINTS
    GET /              — Welcome + identity (useful when the
                          frontend is on a different origin and
                          you want to verify the backend URL)
    GET /health        — Detailed status, including AI readiness
    GET /health/ready  — Minimal readiness probe for load balancers
============================================================
"""

from fastapi import APIRouter

from app.config import settings
from app.services.ai_engine import ai_engine
from app.websocket.manager import connection_manager


router = APIRouter(tags=["Health"])


@router.get("/", summary="Welcome")
async def root() -> dict:
    """Identity check — confirms the backend is reachable."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "environment": settings.app_env,
        "websocket_endpoint": "/ws/session",
        "ai_ready": ai_engine.is_ready,
    }


@router.get("/health", summary="Detailed health check")
async def health_check() -> dict:
    """Detailed status — connection stats + AI engine readiness."""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.app_env,
        "ai_ready": ai_engine.is_ready,
        "connections": {
            "active": connection_manager.active_count,
            "max": settings.ws_max_connections,
        },
        "config": {
            "target_fps": settings.target_fps,
            "max_fps": settings.max_fps,
            "max_frame_size_bytes": settings.max_frame_size_bytes,
        },
    }


@router.get("/health/ready", summary="Readiness probe")
async def readiness_check() -> dict:
    """Trivial 200 OK — used by orchestrators."""
    return {"ready": True}
