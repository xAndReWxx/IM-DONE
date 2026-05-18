"""
============================================================
PhysioAI Pro V2 - Application Settings
============================================================
PURPOSE
    One central place for every tunable knob in the backend.
    Values are loaded from environment variables (with a .env
    file for local development), validated by Pydantic, and
    exposed as a singleton imported across the app.

WHY PYDANTIC SETTINGS?
    - Catches misconfiguration at startup, not at runtime
    - Reads .env automatically
    - Each field is typed and documented
    - Easy to override per-environment

NOTE
    In V2 the backend embeds the AI engine in the same Python
    process — no separate microservice — so settings here also
    cover the AI pipeline (FPS targets, posture thresholds, etc).
============================================================
"""

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime settings for the PhysioAI backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Identity ──
    app_name: str = Field(default="PhysioAI Pro V2", description="Display name")
    app_version: str = Field(default="2.0.0", description="Current version")
    app_env: str = Field(default="development", description="development | production")
    debug: bool = Field(default=True, description="Verbose logs, /docs visible")

    # ── Network ──
    host: str = Field(default="0.0.0.0", description="Bind address")
    port: int = Field(default=8000, description="Bind port")

    # ── WebSocket ──
    ws_max_connections: int = Field(default=50, description="Max concurrent clients")
    ws_heartbeat_interval: int = Field(default=30, description="Heartbeat ping (s)")
    ws_max_message_size: int = Field(default=1_048_576, description="Max msg bytes")

    # ── Frame pipeline ──
    max_fps: int = Field(default=25, description="Max processed FPS per client")
    target_fps: int = Field(default=20, description="Target FPS reported to UI")
    max_frame_size_bytes: int = Field(default=524_288, description="Max frame size")

    # ── AI pipeline ──
    # Loaded from the dataset-derived reference JSON at startup; these are
    # defaults that match what the dataset analysis produced.
    ema_alpha_landmarks: float = Field(default=0.5, description="EMA smoothing (0..1)")
    fhp_warn_deg: float = Field(default=22.0, description="Forward head warn cutoff")
    fhp_bad_deg: float = Field(default=30.0, description="Forward head bad cutoff")
    shoulder_tilt_warn_deg: float = Field(default=5.0, description="Shoulder tilt warn")
    shoulder_tilt_bad_deg: float = Field(default=10.0, description="Shoulder tilt bad")
    spine_lean_warn_deg: float = Field(default=6.0, description="Spine lean warn")
    spine_lean_bad_deg: float = Field(default=12.0, description="Spine lean bad")
    hold_duration_seconds: float = Field(default=3.0, description="Rep hold target")

    # MediaPipe model
    mediapipe_model_url: str = Field(
        default="https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
        description="Pose landmarker model URL",
    )
    mediapipe_model_filename: str = Field(
        default="pose_landmarker_full.task",
        description="Local filename for the cached model",
    )

    # ── CORS ──
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://localhost:8080,*",
        description="Comma-separated allowed origins (use * for offline dev)",
    )

    # ── Logging ──
    log_level: str = Field(default="INFO", description="DEBUG | INFO | WARNING | ERROR")
    log_format: str = Field(default="console", description="console | json")

    # ── Derived helpers ──
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


# ── Singleton import target ──
# Usage:  from app.config import settings
settings = Settings()
