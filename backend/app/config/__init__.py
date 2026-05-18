# PhysioAI Pro V2 — Config package
# Re-exports the singleton `settings` for ergonomic imports.

from app.config.settings import settings

__all__ = ["settings"]
