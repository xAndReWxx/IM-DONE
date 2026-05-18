"""
============================================================
PhysioAI Pro V2 - Backend Application Entry Point
============================================================
PURPOSE
    Creates and configures the FastAPI application. This file
    is what uvicorn imports — everything wires together here:

        FastAPI()
          + lifespan (startup/shutdown hooks)
          + CORS middleware
          + global error handlers
          + HTTP routes (health)
          + WebSocket routes (/ws/session)
          + Static files: /exercise_videos → backend/exercise_videos/

RUNNING
    Development:
        uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

    Production (single worker — see WebSocket note below):
        uvicorn app.main:app --workers 1 --host 0.0.0.0 --port 8000

WEBSOCKET WORKER NOTE
    WebSocket connections are stateful and pinned to whichever
    process accepted the handshake. Multi-worker uvicorn would
    split clients across processes, breaking the in-memory
    ConnectionManager. For scale-out, run multiple servers
    behind a sticky load balancer instead.
============================================================
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.events import lifespan
from app.middleware import setup_error_handlers
from app.routers import health_router, ws_router

# The exercise_videos folder sits at backend/exercise_videos/.
_BACKEND_ROOT  = Path(__file__).resolve().parents[1]  # → physioai-v2/backend/
_EXERCISE_VIDEOS_DIR = _BACKEND_ROOT / "exercise_videos"
_EXERCISE_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)


def create_app() -> FastAPI:
    """
    Application factory. Builds a fully configured FastAPI instance.
    """

    # ── Create app ──
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Realtime AI-powered physiotherapy posture tracking system. "
            "Accepts camera frames via WebSocket and returns pose analysis, "
            "posture scoring, exercise recommendations, and Arabic coaching."
        ),
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # ── CORS ──
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global error handlers ──
    setup_error_handlers(application)

    # ── Routers ──
    application.include_router(health_router)
    application.include_router(ws_router)

    # ── Static files: exercise videos ──
    # Mounted AFTER the routers so the path `/exercise_videos` doesn't
    # conflict with any API routes.
    application.mount(
        "/exercise_videos",
        StaticFiles(directory=str(_EXERCISE_VIDEOS_DIR)),
        name="exercise_videos",
    )

    return application


# What uvicorn imports: `uvicorn app.main:app`
app = create_app()
