# PhysioAI Pro V2 — WebSocket package
# Connection manager singleton + per-connection handler function.

from app.websocket.manager import connection_manager
from app.websocket.handler import websocket_handler

__all__ = ["connection_manager", "websocket_handler"]
