"""
============================================================
PhysioAI Pro V2 - Utility Helpers
============================================================
PURPOSE
    Small, pure, side-effect-free helpers used across the app.
    Keeping them in one place avoids duplication (every module
    that needed a client ID would reimplement it slightly
    differently otherwise).
============================================================
"""

import time
import uuid


def generate_client_id() -> str:
    """
    Unique per-connection identifier, short enough to grep in logs.
    Example: 'client_a1b2c3d4'
    """
    return f"client_{uuid.uuid4().hex[:8]}"


def get_timestamp_ms() -> int:
    """Current Unix time in milliseconds (used for latency math)."""
    return int(time.time() * 1000)


def calculate_latency_ms(client_timestamp_seconds: float) -> int:
    """
    Latency between client frame capture and server processing.

    Clamped to 0 — clock drift between client and server can
    produce negative values which would confuse the dashboard.
    """
    if client_timestamp_seconds <= 0:
        return 0
    client_ms = int(client_timestamp_seconds * 1000)
    return max(0, get_timestamp_ms() - client_ms)


def bytes_to_human(size_bytes: int) -> str:
    """Pretty-print a byte count: 1024 -> '1.0 KB'."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
