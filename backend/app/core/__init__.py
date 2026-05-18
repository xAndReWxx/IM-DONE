# PhysioAI Pro V2 — Core package
# Application-wide cross-cutting concerns: lifecycle events, custom exceptions.

from app.core.exceptions import (
    PhysioAIError,
    FrameValidationError,
    ConnectionLimitError,
    AIEngineError,
    PacketParseError,
)
from app.core.events import lifespan

__all__ = [
    "PhysioAIError",
    "FrameValidationError",
    "ConnectionLimitError",
    "AIEngineError",
    "PacketParseError",
    "lifespan",
]
