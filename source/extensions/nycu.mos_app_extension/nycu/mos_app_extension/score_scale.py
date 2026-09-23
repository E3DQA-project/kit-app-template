"""Shared normalization for the MOS five-anchor half-step scale."""

from __future__ import annotations

from math import floor, isfinite
from typing import Any


def normalize_score(value: Any) -> float:
    """Return a score in the inclusive 1.0–5.0 range, snapped to 0.5."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 3.0
    if not isfinite(score):
        score = 3.0
    score = max(1.0, min(5.0, score))
    return floor(score * 2 + 0.5) / 2


def score_from_slider_value(value: Any) -> float:
    """Convert the slider's integer 2–10 domain to a MOS half-score."""
    try:
        slider_value = int(value)
    except (TypeError, ValueError):
        slider_value = 6
    return normalize_score(slider_value / 2)


def slider_value_from_score(value: Any) -> int:
    """Convert a MOS score to the slider's integer 2–10 domain."""
    return int(normalize_score(value) * 2)
