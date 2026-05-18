"""
============================================================
PhysioAI Pro V2 - WebSocket Routes
============================================================
PURPOSE
    Declares the single realtime endpoint. The route is a tiny
    shim that delegates to `websocket_handler` — keeping the
    actual logic out of the FastAPI router layer.

ENDPOINT PATH
    /ws/session  — chosen to match what the frontend already
    constructs (see useSessionSocket in App.tsx). If you change
    it here, update the frontend's WS URL too.
============================================================
"""

from fastapi import APIRouter, WebSocket

from app.websocket.handler import websocket_handler


router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/session")
async def session_websocket_endpoint(websocket: WebSocket):
    """
    Realtime pose-streaming endpoint.

    Protocol (high-level):
      1. Client connects to ws://host:port/ws/session
      2. Server accepts and sends a `connected` packet with config
      3. Client streams `frame` packets (base64 JPEG)
      4. Server replies with `pose_result` packets per processed frame
      5. Client may send `select_exercise`, `reset_reps`, `heartbeat`
      6. Either side may close at any time
    """
    await websocket_handler(websocket)
