# PhysioAI Pro V2 — Services package
#
# Holds the realtime AI pipeline and the frame router that fronts it.
# The websocket handler depends on these singletons.

from app.services.ai_engine import ai_engine
from app.services.frame_router import frame_router

__all__ = ["ai_engine", "frame_router"]
