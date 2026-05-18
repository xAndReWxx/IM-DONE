"""
============================================================
PhysioAI Pro V2 - Geometry Helpers
============================================================
PURPOSE
    Pure math: angles between landmarks, vertical-axis angles,
    and distance helpers. Everything here is stateless and
    operates on lists/tuples of floats so it's easy to test.

NOTE ON COORDINATES
    MediaPipe gives normalized image coordinates:
      x ∈ [0, 1] — left → right
      y ∈ [0, 1] — top  → bottom  (NOTE: Y axis grows downward,
                                   like all 2D image conventions)
      z          — relative depth, negative = closer to camera
    All angles below assume that convention.
============================================================
"""

import math
from typing import Sequence

import numpy as np


# Type alias for a 2D-or-3D point (we only care about [x, y] for most calcs)
Point = Sequence[float]


def calculate_angle(a: Point, b: Point, c: Point) -> float:
    """
    Interior angle at vertex b for three points a-b-c (degrees).

    Common use: knee angle, elbow angle, chin-shoulder-hip angle, etc.
    Returns 0 if any side vector has zero length (degenerate triangle).
    """
    a_arr = np.array(a, dtype=float)
    b_arr = np.array(b, dtype=float)
    c_arr = np.array(c, dtype=float)

    ba = a_arr - b_arr
    bc = c_arr - b_arr

    denom = (np.linalg.norm(ba) * np.linalg.norm(bc)) + 1e-9
    cos_t = float(np.dot(ba, bc) / denom)
    cos_t = max(-1.0, min(1.0, cos_t))
    return float(math.degrees(math.acos(cos_t)))


def calculate_angle_2d(a: Point, b: Point, c: Point) -> float:
    """Same as calculate_angle but ignores z, using only x,y."""
    return calculate_angle(a[:2], b[:2], c[:2])


def vertical_angle(a: Point, b: Point) -> float:
    """
    Angle of the segment a→b relative to the screen's vertical axis (degrees).

    Used heavily for forward-head detection (ear-to-shoulder vector) and
    spine-lean detection (shoulder-midpoint to hip-midpoint vector).

    Returns 0 if the segment is perfectly vertical; grows toward 90° as
    it becomes more horizontal.
    """
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    return float(math.degrees(math.atan2(abs(dx), abs(dy) + 1e-9)))


def horizontal_tilt(a: Point, b: Point) -> float:
    """
    Tilt of the horizontal segment a-b relative to a true horizontal line
    (degrees). Used for shoulder tilt (left_shoulder ↔ right_shoulder).

    Returns 0 for a perfectly level segment, ~90 for a vertical one.
    """
    dx = float(b[0]) - float(a[0])
    dy = float(b[1]) - float(a[1])
    return float(math.degrees(math.atan2(abs(dy), abs(dx) + 1e-9)))


def midpoint(a: Point, b: Point) -> tuple[float, float]:
    """2D midpoint of two points."""
    return ((float(a[0]) + float(b[0])) / 2.0, (float(a[1]) + float(b[1])) / 2.0)

