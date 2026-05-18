"""
============================================================
PhysioAI Pro V2 - WebSocket Message Handler
============================================================
PURPOSE
    The entire lifecycle for a single WebSocket client:
        connect → loop[parse + route] → cleanup

    Lives outside the FastAPI router so the routing layer stays
    thin and the handler is testable without spinning up FastAPI.

MESSAGE TYPES SUPPORTED (CLIENT → SERVER)
    frame             — camera JPEG; runs the AI pipeline
    select_exercise   — switch the tracked exercise
    reset_reps        — zero the current rep counter
    heartbeat         — keep-alive ping; we reply with a pong
    start_scan        — begin a 360° posture scan
    scan_phase_data   — landmark snapshot for one scan phase

ERROR PHILOSOPHY
    A single bad message must not kill the connection. The loop
    catches everything, sends a structured error packet, and
    keeps reading. Only WebSocketDisconnect ends the session.
============================================================
"""

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.exceptions import (
    PhysioAIError,
    PacketParseError,
    FrameValidationError,
)
from app.models.packets import (
    FramePacket,
    HeartbeatPacket,
    SelectExercisePacket,
    ResetRepsPacket,
    StartScanPacket,
    ScanPhaseDataPacket,
    StartCalibrationPacket,
    StopCalibrationPacket,
    PacketType,
)
from app.services.ai_engine import ai_engine
from app.services.frame_router import frame_router
from app.services.calibration.guided_scan_controller import GuidedScanController
from app.utils.logger import get_logger
from app.utils.helpers import get_timestamp_ms
from app.websocket.manager import connection_manager


logger = get_logger(__name__)

# Per-client calibration controllers.
_calibration_controllers: dict[str, GuidedScanController] = {}


# ====================================================================
# TOP-LEVEL HANDLER
# ====================================================================

async def websocket_handler(websocket: WebSocket) -> None:
    """
    Manages one WebSocket connection end-to-end.
    """
    client_id: str | None = None

    try:
        # ── PHASE 1: Accept + send config ──
        client_id = await connection_manager.connect(websocket)

        await connection_manager.send_json(client_id, {
            "type": PacketType.CONNECTED.value,
            "client_id": client_id,
            "config": {
                "max_fps": settings.max_fps,
                "target_fps": settings.target_fps,
                "max_frame_size": settings.max_frame_size_bytes,
                "heartbeat_interval": settings.ws_heartbeat_interval,
                "ai_ready": ai_engine.is_ready,
            },
            "message": "Connected to PhysioAI Pro V2",
        })

        # ── PHASE 2: Main loop ──
        await _message_loop(websocket, client_id)

    except ConnectionError:
        logger.warning("connection_rejected_limit", client_id=client_id)
        try:
            await websocket.close(code=1013, reason="Server at capacity")
        except Exception:
            pass

    except WebSocketDisconnect as e:
        logger.info("client_disconnect_normal", client_id=client_id, code=e.code)

    except Exception as e:
        logger.error(
            "handler_unexpected_error",
            client_id=client_id,
            error=str(e),
            error_type=type(e).__name__,
        )

    finally:
        if client_id:
            # Clean up calibration controller.
            _calibration_controllers.pop(client_id, None)
            await connection_manager.disconnect(client_id)


# ====================================================================
# MESSAGE LOOP
# ====================================================================

async def _message_loop(websocket: WebSocket, client_id: str) -> None:
    """
    Read messages until the client disconnects. Each iteration
    parses one message and dispatches to the right handler.
    Errors are caught and surfaced as structured packets.
    """
    while True:
        try:
            raw_message = await websocket.receive_text()

            connection_manager.update_metadata(
                client_id,
                last_activity=asyncio.get_event_loop().time(),
            )

            await _process_message(raw_message, client_id)

        except WebSocketDisconnect:
            raise

        except json.JSONDecodeError as e:
            logger.warning("invalid_json", client_id=client_id, error=str(e))
            await connection_manager.send_error(
                client_id, "INVALID_JSON", "Message is not valid JSON", str(e)
            )

        except PacketParseError as e:
            logger.warning("invalid_packet", client_id=client_id, error=e.message)
            await connection_manager.send_error(client_id, e.code, e.message)

        except FrameValidationError as e:
            logger.warning("frame_validation_failed", client_id=client_id, error=e.message)
            await connection_manager.send_error(client_id, e.code, e.message)

        except PhysioAIError as e:
            logger.error("application_error", client_id=client_id, code=e.code, error=e.message)
            await connection_manager.send_error(client_id, e.code, e.message)

        except Exception as e:
            logger.error(
                "unexpected_processing_error",
                client_id=client_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            await connection_manager.send_error(
                client_id, "INTERNAL_ERROR", "An unexpected error occurred"
            )


# ====================================================================
# DISPATCH
# ====================================================================

async def _process_message(raw_message: str, client_id: str) -> None:
    """Parse JSON, check `type`, route to the right handler."""
    data = json.loads(raw_message)

    packet_type = data.get("type")
    if not packet_type:
        raise PacketParseError("Missing 'type' field in packet")

    if packet_type == PacketType.FRAME.value:
        await _handle_frame(data, client_id)
    elif packet_type == PacketType.SELECT_EXERCISE.value:
        await _handle_select_exercise(data, client_id)
    elif packet_type == PacketType.RESET_REPS.value:
        await _handle_reset_reps(data, client_id)
    elif packet_type == PacketType.HEARTBEAT.value:
        await _handle_heartbeat(data, client_id)
    elif packet_type == PacketType.START_SCAN.value:
        await _handle_start_scan(data, client_id)
    elif packet_type == PacketType.SCAN_PHASE_DATA.value:
        await _handle_scan_phase_data(data, client_id)
    elif packet_type == PacketType.START_CALIBRATION.value:
        await _handle_start_calibration(data, client_id)
    elif packet_type == PacketType.STOP_CALIBRATION.value:
        await _handle_stop_calibration(data, client_id)
    else:
        raise PacketParseError(f"Unknown packet type: '{packet_type}'")


# ====================================================================
# INDIVIDUAL HANDLERS
# ====================================================================

async def _handle_frame(data: dict, client_id: str) -> None:
    """Run a JPEG frame through the AI pipeline + calibration if active."""
    start_time = get_timestamp_ms()

    try:
        frame_packet = FramePacket(**data)
    except Exception as e:
        raise FrameValidationError(f"Invalid frame packet: {e}")

    connection_manager.increment_counter(client_id, "frames_received")

    result = await frame_router.process_frame(frame_packet, client_id)

    processing_time = get_timestamp_ms() - start_time
    result["latency_ms"] = processing_time

    connection_manager.increment_counter(client_id, "frames_processed")
    await connection_manager.send_json(client_id, result)

    logger.debug(
        "frame_processed",
        client_id=client_id,
        latency_ms=processing_time,
        posture_score=result.get("posture_score"),
        skipped=result.get("skipped", False),
    )

    # ── Calibration processing (piggybacks on the frame) ──
    controller = _calibration_controllers.get(client_id)
    if controller and controller.is_active:
        # Extract landmarks from the pose result for calibration.
        import numpy as np
        landmarks_raw = result.get("landmarks")
        cal_landmarks = None
        if landmarks_raw and isinstance(landmarks_raw, list) and len(landmarks_raw) == 33:
            cal_landmarks = np.array(
                [[lm["x"], lm["y"], lm["z"], lm["visibility"]] for lm in landmarks_raw],
                dtype=np.float32,
            )

        cal_update = controller.process(cal_landmarks)
        await connection_manager.send_json(client_id, cal_update.to_dict())

        # If a phase was just captured, store it in the AI engine.
        if cal_update.phase_just_captured and cal_update.captured_landmarks:
            ai_engine.store_scan_phase(
                client_id,
                cal_update.phase_just_captured,
                cal_update.captured_landmarks,
            )

        # If calibration reached PROCESSING state, run 360° analysis.
        if cal_update.state == "processing" and ai_engine.scan_buffer_complete(client_id):
            scan_result = await ai_engine.analyze_360_scan(client_id)
            await connection_manager.send_json(client_id, scan_result)
            logger.info("calibration_scan_result_sent", client_id=client_id)

            # Mark calibration complete.
            complete_update = controller.mark_processing_complete()
            await connection_manager.send_json(client_id, complete_update.to_dict())

            # Remove controller — calibration is done.
            _calibration_controllers.pop(client_id, None)


async def _handle_select_exercise(data: dict, client_id: str) -> None:
    """Switch the tracked exercise for this client."""
    pkt = SelectExercisePacket(**data)
    ok = ai_engine.select_exercise(client_id, pkt.exercise_id)
    if not ok:
        await connection_manager.send_error(
            client_id, "UNKNOWN_EXERCISE", f"Unknown exercise '{pkt.exercise_id}'"
        )


async def _handle_reset_reps(data: dict, client_id: str) -> None:
    """Reset the rep counter for the current exercise."""
    ResetRepsPacket(**data)
    ai_engine.reset_reps(client_id)


async def _handle_heartbeat(data: dict, client_id: str) -> None:
    """Reply with a heartbeat pong."""
    HeartbeatPacket(**data)
    await connection_manager.send_json(client_id, {
        "type": PacketType.HEARTBEAT.value,
        "timestamp": get_timestamp_ms() / 1000.0,
        "server_time": get_timestamp_ms(),
    })


async def _handle_start_scan(data: dict, client_id: str) -> None:
    """Acknowledge the scan start; the client drives the phase flow."""
    StartScanPacket(**data)
    # Reset any accumulated scan buffer for this client.
    ai_engine.reset_scan_buffer(client_id)
    logger.info("scan_started", client_id=client_id)


async def _handle_scan_phase_data(data: dict, client_id: str) -> None:
    """
    Store one phase's landmarks in the scan buffer.
    When all four directional phases have been received, run the
    full-body analysis and send back a scan_result.
    """
    pkt = ScanPhaseDataPacket(**data)
    ai_engine.store_scan_phase(client_id, pkt.phase, pkt.landmarks)

    logger.debug("scan_phase_received", client_id=client_id, phase=pkt.phase)

    # Check if we have enough phases to analyze.
    if ai_engine.scan_buffer_complete(client_id):
        result = await ai_engine.analyze_360_scan(client_id)
        await connection_manager.send_json(client_id, result)
        logger.info("scan_result_sent", client_id=client_id)


async def _handle_start_calibration(data: dict, client_id: str) -> None:
    """
    Start the AI-guided calibration pipeline.
    Creates a per-client GuidedScanController and sends the
    initial calibration_update.
    """
    StartCalibrationPacket(**data)

    # Reset any existing calibration for this client.
    controller = GuidedScanController()
    _calibration_controllers[client_id] = controller

    # Also reset the scan buffer in the AI engine.
    ai_engine.reset_scan_buffer(client_id)

    initial_update = controller.start()
    await connection_manager.send_json(client_id, initial_update.to_dict())
    logger.info("calibration_started", client_id=client_id)


async def _handle_stop_calibration(data: dict, client_id: str) -> None:
    """Stop/reset the calibration pipeline."""
    StopCalibrationPacket(**data)

    controller = _calibration_controllers.pop(client_id, None)
    if controller:
        controller.reset()
    logger.info("calibration_stopped", client_id=client_id)
