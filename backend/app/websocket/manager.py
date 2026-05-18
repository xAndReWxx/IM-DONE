"""
============================================================
PhysioAI Pro V2 - WebSocket Connection Manager
============================================================
PURPOSE
    Tracks every active WebSocket connection in one place so we
    can:
      • Enforce a max connection count (prevent overload)
      • Send JSON safely (handle disconnects without crashing)
      • Broadcast (future: server-wide notifications)
      • Clean up state on disconnect (prevent memory leaks)

CONCURRENCY
    All mutations to `_connections` happen under `_lock` (asyncio.Lock).
    A single lock is plenty here — the entire connection map fits in
    memory and operations on it are O(1).

WHY ONE WORKER PROCESS?
    WebSocket connections are stateful and pinned to the process
    that accepted them. Running multiple uvicorn workers would
    split clients across processes, breaking this manager. For
    horizontal scaling, run multiple server instances behind a
    sticky load balancer instead.
============================================================
"""

import asyncio
from typing import Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.exceptions import ConnectionLimitError
from app.utils.logger import get_logger
from app.utils.helpers import generate_client_id


logger = get_logger(__name__)


class ConnectionManager:
    """Central registry of every active WebSocket session."""

    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}
        self._metadata: Dict[str, dict] = {}
        self._lock = asyncio.Lock()

    # ── Read-only properties ──

    @property
    def active_count(self) -> int:
        return len(self._connections)

    @property
    def client_ids(self) -> list[str]:
        return list(self._connections.keys())

    # ── Lifecycle ──

    async def connect(self, websocket: WebSocket) -> str:
        """
        Accept the WS handshake and register the connection.

        Raises:
            ConnectionLimitError if we're at capacity.
        """
        async with self._lock:
            if self.active_count >= settings.ws_max_connections:
                logger.warning(
                    "connection_rejected",
                    reason="limit_reached",
                    active=self.active_count,
                    max=settings.ws_max_connections,
                )
                raise ConnectionLimitError(settings.ws_max_connections)

            await websocket.accept()
            client_id = generate_client_id()

            self._connections[client_id] = websocket
            self._metadata[client_id] = {
                "connected_at": asyncio.get_event_loop().time(),
                "frames_received": 0,
                "frames_processed": 0,
                "last_activity": asyncio.get_event_loop().time(),
            }

            logger.info("client_connected", client_id=client_id, active=self.active_count)
            return client_id

    async def disconnect(self, client_id: str) -> None:
        """Tear down one connection. Safe to call multiple times."""
        async with self._lock:
            websocket = self._connections.pop(client_id, None)
            metadata = self._metadata.pop(client_id, {})

            if websocket:
                try:
                    await websocket.close()
                except Exception:
                    pass  # already closed
                logger.info(
                    "client_disconnected",
                    client_id=client_id,
                    active=self.active_count,
                    frames_received=metadata.get("frames_received", 0),
                    frames_processed=metadata.get("frames_processed", 0),
                )

        # Drop per-client state in dependent services (outside the lock).
        try:
            from app.services.ai_engine import ai_engine
            ai_engine.cleanup_client(client_id)
        except Exception:
            pass
        try:
            from app.services.frame_router import frame_router
            frame_router.cleanup_client(client_id)
        except Exception:
            pass

    async def disconnect_all(self) -> None:
        """Close every active connection (graceful shutdown)."""
        ids = list(self._connections.keys())
        logger.info("disconnecting_all_clients", count=len(ids))
        for cid in ids:
            await self.disconnect(cid)
        logger.info("all_clients_disconnected")

    # ── Messaging ──

    async def send_json(self, client_id: str, data: dict) -> bool:
        """
        Send a JSON object to one client. NEVER raises — failures
        are logged and result in `False`. This way one bad client
        can't crash the realtime pipeline.
        """
        websocket = self._connections.get(client_id)
        if not websocket:
            return False
        try:
            await websocket.send_json(data)
            return True
        except WebSocketDisconnect:
            logger.info("send_failed_disconnect", client_id=client_id)
            await self.disconnect(client_id)
            return False
        except Exception as e:
            logger.error("send_failed_error", client_id=client_id, error=str(e))
            await self.disconnect(client_id)
            return False

    async def send_error(
        self,
        client_id: str,
        code: str,
        message: str,
        details: Optional[str] = None,
    ) -> bool:
        """Construct + send a structured error packet."""
        payload = {"type": "error", "code": code, "message": message}
        if details:
            payload["details"] = details
        return await self.send_json(client_id, payload)

    # ── Metadata ──

    def update_metadata(self, client_id: str, **kwargs) -> None:
        if client_id in self._metadata:
            self._metadata[client_id].update(kwargs)

    def get_metadata(self, client_id: str) -> dict:
        return self._metadata.get(client_id, {})

    def increment_counter(self, client_id: str, counter: str) -> None:
        if client_id in self._metadata:
            self._metadata[client_id][counter] = (
                self._metadata[client_id].get(counter, 0) + 1
            )


# ── Singleton ──
connection_manager = ConnectionManager()
