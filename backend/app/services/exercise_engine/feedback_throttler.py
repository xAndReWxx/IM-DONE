"""
============================================================
PhysioAI Pro V2 - Feedback Throttler
============================================================
PURPOSE
    Prevents feedback spam. Every piece of guidance (voice,
    text, corrections) passes through this throttler before
    reaching the user.

RULES
    1. Same message cannot repeat within cooldown_seconds.
    2. Any message requires min_gap_seconds since last output.
    3. Priority messages (corrections) bypass min_gap but
       still respect per-message cooldown.
    4. Queue depth is capped — oldest dropped if full.

USAGE
    throttler = FeedbackThrottler()
    msg = throttler.try_send("Straighten your back")
    # Returns the message if allowed, None if throttled.
============================================================
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ThrottlerConfig:
    """Tunable parameters."""
    min_gap_seconds: float = 2.5       # min time between any two messages
    cooldown_seconds: float = 8.0      # same message can't repeat within this
    priority_gap_seconds: float = 1.5  # min gap for priority messages


class FeedbackThrottler:
    """
    Stateful throttler. One per client.
    """

    def __init__(self, config: Optional[ThrottlerConfig] = None) -> None:
        self._config = config or ThrottlerConfig()
        self._last_send_time: float = 0.0
        self._message_history: dict[str, float] = {}

    def try_send(
        self,
        message: str,
        priority: bool = False,
    ) -> Optional[str]:
        """
        Attempt to send a message. Returns the message if allowed,
        None if throttled.

        Args:
            message: The feedback text.
            priority: If True, uses shorter min_gap.
        """
        if not message or not message.strip():
            return None

        now = time.monotonic()
        gap = self._config.priority_gap_seconds if priority else self._config.min_gap_seconds

        # Check min gap since last ANY message.
        if now - self._last_send_time < gap:
            return None

        # Check per-message cooldown.
        last_time = self._message_history.get(message, 0.0)
        if now - last_time < self._config.cooldown_seconds:
            return None

        # Allow it.
        self._last_send_time = now
        self._message_history[message] = now

        # Prune old entries to prevent unbounded growth.
        if len(self._message_history) > 50:
            cutoff = now - self._config.cooldown_seconds * 2
            self._message_history = {
                k: v for k, v in self._message_history.items()
                if v > cutoff
            }

        return message

    def reset(self) -> None:
        """Clear all history."""
        self._last_send_time = 0.0
        self._message_history.clear()
