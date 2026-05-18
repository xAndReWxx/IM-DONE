"""Tests for the Pydantic packet models."""

import base64

import pytest
from pydantic import ValidationError

from app.models.packets import (
    FramePacket,
    SelectExercisePacket,
    ResetRepsPacket,
    HeartbeatPacket,
)


def _tiny_b64_jpeg() -> str:
    """A minimal valid base64 string (we only check shape, not JPEG)."""
    return base64.b64encode(b"fake-jpeg-bytes").decode()


def test_frame_packet_accepts_valid_input():
    pkt = FramePacket(type="frame", timestamp=1.0, frame=_tiny_b64_jpeg())
    assert pkt.type == "frame"


def test_frame_packet_rejects_wrong_type():
    with pytest.raises(ValidationError):
        FramePacket(type="not_frame", timestamp=1.0, frame=_tiny_b64_jpeg())


def test_frame_packet_rejects_empty_frame():
    with pytest.raises(ValidationError):
        FramePacket(type="frame", timestamp=1.0, frame="")


def test_frame_packet_rejects_bad_timestamp():
    with pytest.raises(ValidationError):
        FramePacket(type="frame", timestamp=-1, frame=_tiny_b64_jpeg())


def test_select_exercise_packet():
    pkt = SelectExercisePacket(type="select_exercise", exercise_id="chin_tuck")
    assert pkt.exercise_id == "chin_tuck"


def test_select_exercise_packet_rejects_wrong_type():
    with pytest.raises(ValidationError):
        SelectExercisePacket(type="frame", exercise_id="chin_tuck")


def test_reset_reps_packet():
    pkt = ResetRepsPacket(type="reset_reps")
    assert pkt.type == "reset_reps"


def test_heartbeat_packet_defaults():
    pkt = HeartbeatPacket()
    assert pkt.type == "heartbeat"
