"""
============================================================
PhysioAI Pro V2 - Custom Exceptions
============================================================
PURPOSE
    Domain-specific exception classes. Each one names a single
    failure mode in the realtime pipeline so callers can react
    precisely (and so logs are immediately understandable).

WHY CUSTOM EXCEPTIONS?
    Generic exceptions ("ValueError: bad frame") force you to
    string-match to figure out what went wrong. Named ones make
    intent obvious and let the WS handler send a structured
    error code back to the client.
============================================================
"""


class PhysioAIError(Exception):
    """Base class for every application-level error."""

    def __init__(self, message: str, code: str = "PHYSIOAI_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class FrameValidationError(PhysioAIError):
    """Frame packet failed validation (bad base64, oversized, etc)."""

    def __init__(self, message: str):
        super().__init__(message=message, code="FRAME_VALIDATION_ERROR")


class ConnectionLimitError(PhysioAIError):
    """Server is at capacity — new connection rejected."""

    def __init__(self, max_connections: int):
        super().__init__(
            message=f"Connection limit reached ({max_connections} max)",
            code="CONNECTION_LIMIT_ERROR",
        )
        self.max_connections = max_connections


class AIEngineError(PhysioAIError):
    """AI pipeline failed (decode error, model error, etc)."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message=message, code="AI_ENGINE_ERROR")
        self.original_error = original_error


class PacketParseError(PhysioAIError):
    """Incoming WS message couldn't be parsed/routed."""

    def __init__(self, message: str):
        super().__init__(message=message, code="PACKET_PARSE_ERROR")
