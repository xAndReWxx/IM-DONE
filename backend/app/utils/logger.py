"""
============================================================
PhysioAI Pro V2 - Structured Logging
============================================================
PURPOSE
    Configure structlog once at import-time. Every module gets
    a logger via `get_logger(__name__)`. Logs include the module
    name and any contextual key/value pairs the caller binds.

WHY STRUCTLOG?
    JSON-able key/value logs are dramatically easier to filter
    and aggregate than raw text. In dev we print colored console
    output; in prod (LOG_FORMAT=json) we emit machine-parseable
    JSON ready for any aggregator (Datadog, Loki, ELK).

USAGE
    from app.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("frame_received", client_id="x", size=1024)
============================================================
"""

import logging
import sys

import structlog

from app.config import settings


def _configure_structlog() -> None:
    """Run once on first import — wires structlog into stdlib logging."""

    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Renderer: JSON for production (or LOG_FORMAT=json), pretty for dev.
    if settings.log_format == "json" or settings.is_production:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Quiet down noisy third-party libs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def get_logger(name: str):
    """
    Returns a bound structlog logger for the calling module.
    Use `__name__` as the argument so logs include the module path.
    """
    return structlog.get_logger(name)


# Configure once at import-time. Subsequent imports reuse this config.
_configure_structlog()
