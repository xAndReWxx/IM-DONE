"""
============================================================
PhysioAI Pro V2 - Phase Detector
============================================================
PURPOSE
    Automatically detect exercise repetition phases from a
    normalized landmark sequence — no manual phase annotation.

ALGORITHM
    1. Compute a "motion signal" from key joint angles.
    2. Smooth the signal (Savitzky-Golay or moving average).
    3. Find peaks and valleys → phase boundaries.
    4. Label phases: REST → CONCENTRIC → PEAK → ECCENTRIC → REST.

    This works for any cyclical exercise (chin tuck, shoulder
    raise, wall angel, etc.) because we work on the dominant
    angle signal rather than exercise-specific logic.

OUTPUTS
    PhaseSequence: list of Phase(start_frame, end_frame, label)
    per_frame_phase: array of phase labels, same length as input
============================================================
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import numpy as np

from app.services.ai.geometry import calculate_angle
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PhaseLabel(str, Enum):
    REST = "rest"
    CONCENTRIC = "concentric"       # moving into exercise
    PEAK = "peak"                   # maximum contraction / hold
    ECCENTRIC = "eccentric"         # returning to rest


@dataclass
class Phase:
    start_frame: int
    end_frame: int
    label: PhaseLabel
    signal_value_start: float = 0.0
    signal_value_end: float = 0.0


@dataclass
class PhaseSequence:
    phases: List[Phase]
    rep_count: int
    signal: np.ndarray              # the raw motion signal
    smoothed_signal: np.ndarray     # smoothed version
    peak_frames: np.ndarray         # frame indices of peaks
    valley_frames: np.ndarray       # frame indices of valleys


# ── Key angle definitions for different exercises ──
# Each entry: (landmark_A, landmark_B_vertex, landmark_C) for calculate_angle
# We pick angles that best capture the exercise's primary motion.
EXERCISE_ANGLES = {
    "chin_tuck": [
        (7, 11, 23),    # left_ear → left_shoulder → left_hip
    ],
    "shoulder_release": [
        (15, 11, 23),   # left_wrist → left_shoulder → left_hip
        (16, 12, 24),   # right_wrist → right_shoulder → right_hip
    ],
    "wall_angel": [
        (15, 11, 23),   # left_wrist → left_shoulder → left_hip
        (16, 12, 24),   # right_wrist → right_shoulder → right_hip
    ],
    "thoracic_extension": [
        (11, 23, 25),   # left_shoulder → left_hip → left_knee
        (12, 24, 26),   # right_shoulder → right_hip → right_knee
    ],
    "t_fly": [
        (15, 11, 23),   # left_wrist → left_shoulder → left_hip
        (16, 12, 24),   # right_wrist → right_shoulder → right_hip
        (13, 11, 23),   # left_elbow → left_shoulder → left_hip
        (14, 12, 24),   # right_elbow → right_shoulder → right_hip
    ],
}

# Fallback: use shoulder-hip-knee angle.
DEFAULT_ANGLES = [
    (11, 23, 25),
    (12, 24, 26),
]


def _compute_motion_signal(
    landmarks: np.ndarray,
    exercise_id: Optional[str] = None,
) -> np.ndarray:
    """
    Compute a 1D motion signal from a (N, 33, 4) landmark sequence.
    Averages the specified joint angles per frame.
    """
    angle_defs = EXERCISE_ANGLES.get(exercise_id or "", DEFAULT_ANGLES)
    n_frames = landmarks.shape[0]
    signal = np.zeros(n_frames, dtype=np.float64)

    for i in range(n_frames):
        lm = landmarks[i]
        # Skip frames with no detection (all zeros).
        if np.allclose(lm[:, :2], 0.0):
            signal[i] = np.nan
            continue

        angles = []
        for a_idx, b_idx, c_idx in angle_defs:
            a = lm[a_idx, :2]
            b = lm[b_idx, :2]
            c = lm[c_idx, :2]
            angle = calculate_angle(a, b, c)
            angles.append(angle)
        signal[i] = np.mean(angles) if angles else 0.0

    # Interpolate NaN gaps.
    nans = np.isnan(signal)
    if nans.any() and not nans.all():
        signal[nans] = np.interp(
            np.where(nans)[0],
            np.where(~nans)[0],
            signal[~nans],
        )

    return signal


def _smooth_signal(signal: np.ndarray, window: int = 7) -> np.ndarray:
    """Moving average smoothing."""
    if len(signal) < window:
        return signal.copy()
    kernel = np.ones(window) / window
    smoothed = np.convolve(signal, kernel, mode="same")
    return smoothed


def _find_peaks_valleys(
    signal: np.ndarray,
    min_prominence: float = 3.0,
    min_distance: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Simple peak/valley detection without scipy dependency.
    Returns (peak_indices, valley_indices).
    """
    peaks = []
    valleys = []
    n = len(signal)

    for i in range(1, n - 1):
        # Check if local maximum.
        if signal[i] > signal[i - 1] and signal[i] > signal[i + 1]:
            # Check prominence: must be higher than both neighbors by min_prominence.
            left_min = np.min(signal[max(0, i - min_distance):i])
            right_min = np.min(signal[i + 1:min(n, i + min_distance + 1)])
            prominence = signal[i] - max(left_min, right_min)
            if prominence >= min_prominence:
                # Check min distance from last peak.
                if not peaks or (i - peaks[-1]) >= min_distance:
                    peaks.append(i)

        # Check if local minimum.
        elif signal[i] < signal[i - 1] and signal[i] < signal[i + 1]:
            left_max = np.max(signal[max(0, i - min_distance):i])
            right_max = np.max(signal[i + 1:min(n, i + min_distance + 1)])
            prominence = min(left_max, right_max) - signal[i]
            if prominence >= min_prominence:
                if not valleys or (i - valleys[-1]) >= min_distance:
                    valleys.append(i)

    return np.array(peaks, dtype=int), np.array(valleys, dtype=int)


def detect_phases(
    landmarks: np.ndarray,
    exercise_id: Optional[str] = None,
    fps: float = 30.0,
) -> PhaseSequence:
    """
    Detect exercise phases from a (N, 33, 4) landmark sequence.

    Returns a PhaseSequence with labeled phases and rep count.
    """
    signal = _compute_motion_signal(landmarks, exercise_id)
    smoothed = _smooth_signal(signal, window=max(3, int(fps * 0.2)))

    # Determine if exercise signal goes UP during concentric or DOWN.
    # Use the first valley-to-peak direction.
    peaks, valleys = _find_peaks_valleys(smoothed, min_prominence=4.0, min_distance=int(fps * 0.3))

    phases: List[Phase] = []
    rep_count = 0

    if len(peaks) == 0 and len(valleys) == 0:
        # No clear reps — mark entire sequence as REST.
        phases.append(Phase(0, len(signal) - 1, PhaseLabel.REST))
        return PhaseSequence(phases, 0, signal, smoothed, peaks, valleys)

    # Merge peaks and valleys into alternating sequence.
    events = []
    for p in peaks:
        events.append((p, "peak"))
    for v in valleys:
        events.append((v, "valley"))
    events.sort(key=lambda x: x[0])

    # Build phases from event pairs.
    # Starting rest period.
    if events[0][0] > 0:
        phases.append(Phase(0, events[0][0] - 1, PhaseLabel.REST,
                            smoothed[0], smoothed[events[0][0] - 1]))

    for i in range(len(events)):
        frame, event_type = events[i]
        next_frame = events[i + 1][0] if i + 1 < len(events) else len(signal) - 1

        if event_type == "valley":
            # Valley → next event = concentric (moving toward peak)
            phases.append(Phase(frame, next_frame, PhaseLabel.CONCENTRIC,
                                smoothed[frame], smoothed[next_frame]))
        elif event_type == "peak":
            # Peak → PEAK (short hold region)
            peak_end = min(frame + max(1, int(fps * 0.1)), next_frame)
            phases.append(Phase(frame, peak_end, PhaseLabel.PEAK,
                                smoothed[frame], smoothed[peak_end]))
            # Then eccentric until next valley/event.
            if peak_end < next_frame:
                phases.append(Phase(peak_end, next_frame, PhaseLabel.ECCENTRIC,
                                    smoothed[peak_end], smoothed[next_frame]))
            rep_count += 1

    # Trailing rest.
    last_event_frame = events[-1][0]
    if last_event_frame < len(signal) - 1:
        phases.append(Phase(last_event_frame + 1, len(signal) - 1, PhaseLabel.REST,
                            smoothed[last_event_frame + 1], smoothed[-1]))

    logger.info(
        "phases_detected",
        exercise=exercise_id,
        reps=rep_count,
        n_phases=len(phases),
        n_peaks=len(peaks),
        n_valleys=len(valleys),
    )

    return PhaseSequence(phases, rep_count, signal, smoothed, peaks, valleys)


def get_per_frame_labels(
    phase_seq: PhaseSequence,
    n_frames: int,
) -> np.ndarray:
    """
    Convert a PhaseSequence to per-frame label array (for comparison).
    Returns array of shape (n_frames,) with integer labels:
      0=rest, 1=concentric, 2=peak, 3=eccentric
    """
    LABEL_MAP = {
        PhaseLabel.REST: 0,
        PhaseLabel.CONCENTRIC: 1,
        PhaseLabel.PEAK: 2,
        PhaseLabel.ECCENTRIC: 3,
    }
    labels = np.zeros(n_frames, dtype=np.int8)
    for phase in phase_seq.phases:
        start = max(0, phase.start_frame)
        end = min(n_frames - 1, phase.end_frame)
        labels[start:end + 1] = LABEL_MAP.get(phase.label, 0)
    return labels
