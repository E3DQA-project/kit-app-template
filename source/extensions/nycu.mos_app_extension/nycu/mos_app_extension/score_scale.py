"""Shared normalization for the MOS five-anchor half-step scale."""

from __future__ import annotations

from typing import Any


def normalize_score(value: Any) -> float:
    """Return a score in the inclusive 1.0–5.0 range, snapped to 0.5."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 3.0
    score = max(1.0, min(5.0, score))
    return round(score * 2) / 2
