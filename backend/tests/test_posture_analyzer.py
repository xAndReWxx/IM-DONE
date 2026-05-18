"""Sanity tests for the posture analyzer using known reference data."""

import json
from pathlib import Path

import numpy as np

from app.services.ai.posture_analyzer import PostureAnalyzer


def _good_posture_landmarks() -> np.ndarray:
    """Load the reference good-posture landmarks from the dataset JSON."""
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "reference"
        / "good_posture_reference.json"
    )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    landmarks = data["good_posture_landmarks"]
    arr = np.array(
        [[lm["x"], lm["y"], lm["z"], lm["visibility"]] for lm in landmarks],
        dtype=np.float32,
    )
    assert arr.shape == (33, 4)
    return arr


def test_analyzer_initializes():
    a = PostureAnalyzer()
    assert a is not None


def test_good_posture_scores_high():
    """The dataset baseline 'rest' pose should score well above 80."""
    a = PostureAnalyzer()
    result = a.analyze(_good_posture_landmarks())
    assert result.score >= 80, f"Expected ≥80, got {result.score}"


def test_missing_landmarks_returns_neutral():
    """Less than 33 landmarks → neutral output, no crash."""
    a = PostureAnalyzer()
    result = a.analyze(np.zeros((10, 4), dtype=np.float32))
    assert result.score == 0
    assert result.issues == []


def test_strongly_tilted_shoulders_flags_issue():
    """Synthesize a pose with one shoulder much lower than the other."""
    landmarks = _good_posture_landmarks().copy()
    # Drop the right shoulder dramatically.
    landmarks[12][1] += 0.20
    a = PostureAnalyzer()
    result = a.analyze(landmarks)
    assert "rounded_shoulders" in result.issues
    assert result.feedback_ar != ""
