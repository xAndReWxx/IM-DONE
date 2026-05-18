"""
============================================================
PhysioAI Pro V2 - Global HTTP Error Handlers
============================================================
PURPOSE
    Convert uncaught exceptions on HTTP routes into structured
    JSON responses. Keeps the API predictable for clients and
    prevents raw stack traces from leaking in production.

NOTE
    These handlers only apply to HTTP routes. WebSocket errors
    are handled inside the WS handler itself — middleware doesn't
    apply to ASGI scope `websocket`.
============================================================
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.core.exceptions import PhysioAIError
from app.utils.logger import get_logger

logger = get_logger(__name__)


def setup_error_handlers(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI app."""

    @app.exception_handler(PhysioAIError)
    async def physioai_error_handler(request: Request, exc: PhysioAIError) -> JSONResponse:
        """App-specific errors — return code + message."""
        logger.error(
            "application_error",
            code=exc.code,
            message=exc.message,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=400,
            content={"error": True, "code": exc.code, "message": exc.message},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Standard HTTP errors (404, 405, etc.) — uniform JSON shape."""
        logger.warning(
            "http_error",
            status_code=exc.status_code,
            detail=exc.detail,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Catch-all. In development we leak the error string for
        debuggability; in production we say "An unexpected error
        occurred" so we don't expose stack-trace details.
        """
        logger.error(
            "unhandled_exception",
            error=str(exc),
            error_type=type(exc).__name__,
            path=str(request.url),
            exc_info=True,
        )
        message = f"Internal error: {exc}" if settings.is_development else "An unexpected error occurred"
        return JSONResponse(
            status_code=500,
            content={"error": True, "code": "INTERNAL_ERROR", "message": message},
        )
