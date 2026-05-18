# PhysioAI Pro V2 — Calibration subpackage
# Dynamic AI Guided Calibration System for intelligent posture scanning.
#
# Replaces the old timer-based scan workflow with a fully
# condition-driven FSM that validates body visibility,
# orientation, stability, and confidence before capturing
# each scan phase.

from app.services.calibration.scan_fsm import (
    CalibrationState,
    CalibrationFSM,
)
from app.services.calibration.body_validator import BodyValidator, BodyValidationResult
from app.services.calibration.orientation_detector import (
    Orientation,
    OrientationDetector,
    OrientationResult,
)
from app.services.calibration.stability_detector import StabilityDetector, StabilityResult
from app.services.calibration.confidence_analyzer import ConfidenceAnalyzer, ConfidenceResult
from app.services.calibration.guided_scan_controller import GuidedScanController

__all__ = [
    "CalibrationState",
    "CalibrationFSM",
    "BodyValidator",
    "BodyValidationResult",
    "Orientation",
    "OrientationDetector",
    "OrientationResult",
    "StabilityDetector",
    "StabilityResult",
    "ConfidenceAnalyzer",
    "ConfidenceResult",
    "GuidedScanController",
]
