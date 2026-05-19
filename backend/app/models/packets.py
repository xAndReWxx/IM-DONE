"""
============================================================
PhysioAI Pro V2 - WebSocket Packet Models
============================================================
PURPOSE
    Strict Pydantic models for every message that crosses the
    WebSocket boundary. Validation happens BEFORE any business
    logic, so the AI engine never receives malformed input.

WIRE CONTRACT (must stay in lockstep with the frontend)
    CLIENT → SERVER
        • {type:"frame", timestamp, frame}           — JPEG frame
        • {type:"select_exercise", exercise_id}      — switch tracked exercise
        • {type:"reset_reps"}                        — zero rep counter
        • {type:"heartbeat"}                         — keep-alive

    SERVER → CLIENT
        • {type:"connected", client_id, config}   — handshake reply
        • {type:"pose_result", ...}               — main per-frame payload
        • {type:"scan_result", ...}               — front scan analysis
        • {type:"error", code, message}           — structured error
        • {type:"heartbeat", server_time}         — keep-alive pong

WHY USE A PacketType ENUM?
    Prevents typos in `if msg.type == "fram"` from silently
    becoming dead code. Enum members are checked at class load.
============================================================
"""

import base64
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.config import settings


class PacketType(str, Enum):
    """All packet types used on the wire."""
    # Client → Server
    FRAME = "frame"
    SELECT_EXERCISE = "select_exercise"
    RESET_REPS = "reset_reps"
    HEARTBEAT = "heartbeat"
    START_CALIBRATION = "start_calibration"
    STOP_CALIBRATION = "stop_calibration"
    # Server → Client
    CONNECTED = "connected"
    POSE_RESULT = "pose_result"
    SCAN_RESULT = "scan_result"
    CALIBRATION_UPDATE = "calibration_update"
    ERROR = "error"


# ============================================================
# CLIENT → SERVER
# ============================================================

class FramePacket(BaseModel):
    """
    A single camera frame (base64-encoded JPEG) from the client.

    Validation rules:
      • type must literally equal "frame"
      • timestamp must be positive
      • frame must decode as valid base64
      • decoded byte size must be ≤ settings.max_frame_size_bytes
    """
    type: str = Field(..., description="Must be 'frame'")
    timestamp: float = Field(..., description="Client capture time (seconds)")
    frame: str = Field(..., description="Base64-encoded JPEG bytes")

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v != PacketType.FRAME.value:
            raise ValueError(f"Expected type 'frame', got '{v}'")
        return v

    @field_validator("timestamp")
    @classmethod
    def _ts(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Timestamp must be positive")
        return v

    @field_validator("frame")
    @classmethod
    def _frame(cls, v: str) -> str:
        if not v:
            raise ValueError("Frame data cannot be empty")
        try:
            decoded = base64.b64decode(v, validate=False)
        except Exception:
            raise ValueError("Frame is not valid base64")
        if len(decoded) > settings.max_frame_size_bytes:
            from app.utils.helpers import bytes_to_human
            raise ValueError(
                f"Frame size {bytes_to_human(len(decoded))} exceeds "
                f"max {bytes_to_human(settings.max_frame_size_bytes)}"
            )
        return v


class SelectExercisePacket(BaseModel):
    """Switch the actively tracked exercise (and zero the counter)."""
    type: str = Field(..., description="Must be 'select_exercise'")
    exercise_id: str = Field(..., description="One of: chin_tuck, wall_angel, thoracic_extension")

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v != PacketType.SELECT_EXERCISE.value:
            raise ValueError(f"Expected 'select_exercise', got '{v}'")
        return v


class ResetRepsPacket(BaseModel):
    """Reset the rep counter for the currently selected exercise."""
    type: str = Field(..., description="Must be 'reset_reps'")

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v != PacketType.RESET_REPS.value:
            raise ValueError(f"Expected 'reset_reps', got '{v}'")
        return v


class HeartbeatPacket(BaseModel):
    """Keep-alive — mobile/proxy networks close idle WS connections fast."""
    type: str = Field(default=PacketType.HEARTBEAT.value)
    timestamp: Optional[float] = None

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v != PacketType.HEARTBEAT.value:
            raise ValueError(f"Expected 'heartbeat', got '{v}'")
        return v


class StartCalibrationPacket(BaseModel):
    """Signal that the client wants to begin AI-guided calibration."""
    type: str = Field(..., description="Must be 'start_calibration'")

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v != PacketType.START_CALIBRATION.value:
            raise ValueError(f"Expected 'start_calibration', got '{v}'")
        return v


class StopCalibrationPacket(BaseModel):
    """Signal that the client wants to stop/reset calibration."""
    type: str = Field(..., description="Must be 'stop_calibration'")

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v != PacketType.STOP_CALIBRATION.value:
            raise ValueError(f"Expected 'stop_calibration', got '{v}'")
        return v
# ============================================================
# SERVER → CLIENT
# ============================================================

class LandmarkPoint(BaseModel):
    """
    One MediaPipe body landmark.

    Coordinates are normalized to [0, 1] relative to the frame.
    z is relative depth (negative = closer to camera).
    visibility is the model's confidence the joint was seen.
    """
    x: float
    y: float
    z: float = 0.0
    visibility: float = 0.0


class ExerciseCard(BaseModel):
    """
    A recommended exercise. Shown as a card in the UI; selected
    one becomes the actively tracked exercise.
    """
    id: str = Field(..., description="Stable ID, e.g. 'chin_tuck'")
    name_ar: str = Field(..., description="Arabic display name")
    name_en: str = Field(..., description="English display name")
    reps: int = Field(..., description="Recommended rep count")
    duration_s: int = Field(..., description="Estimated duration (s)")
    instructions_ar: List[str] = Field(default_factory=list, description="Step-by-step (Arabic)")


class RepState(BaseModel):
    """Current rep counter / FSM phase for the selected exercise."""
    exercise_id: str
    reps: int
    phase: str = Field(..., description="idle | active | hold | returning")
    last_feedback_ar: str = ""


class PoseResultPacket(BaseModel):
    """
    Main payload sent back to the client for every processed frame.

    The frontend reads ALL of these fields; keep this schema stable
    or update the frontend's PoseResultMessage type in lockstep.
    """
    type: str = Field(default=PacketType.POSE_RESULT.value)
    fps: float = Field(default=0.0, description="Smoothed processing FPS")
    landmarks: Optional[List[LandmarkPoint]] = Field(default=None)
    posture_score: Optional[int] = Field(default=None, description="0-100 (None if no pose)")
    posture_issues: List[str] = Field(default_factory=list, description="e.g. ['forward_head']")
    feedback_ar: str = Field(default="", description="Arabic coaching line for TTS")
    recommendations: List[ExerciseCard] = Field(default_factory=list)
    rep_state: Optional[RepState] = Field(default=None)
    latency_ms: int = Field(default=0)
    exercise_correction: Optional[str] = Field(
        default=None,
        description="English correction instruction when exercise form deviates",
    )


class ScanIssue(BaseModel):
    """One issue detected during the 360° scan."""
    type: str
    description: str
    severity: str = Field(default="mild", description="mild | moderate | severe")


class ScanResultPacket(BaseModel):
    """Full-body analysis result returned after a complete 360° scan."""
    type: str = Field(default=PacketType.SCAN_RESULT.value)
    posture_score: int = Field(default=0)
    issues: List[ScanIssue] = Field(default_factory=list)
    recommendations: List[ExerciseCard] = Field(default_factory=list)
    analysis_summary: str = Field(default="")


class ConnectedPacket(BaseModel):
    """Handshake reply sent immediately after a client connects."""
    type: str = Field(default=PacketType.CONNECTED.value)
    client_id: str
    config: dict


class ErrorPacket(BaseModel):
    """Structured error sent when the server can't fulfill a request."""
    type: str = Field(default=PacketType.ERROR.value)
    code: str
    message: str
    details: Optional[str] = None
