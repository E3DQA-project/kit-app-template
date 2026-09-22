"""Small, Kit-independent helpers for Matrix-3D camera poses."""

from __future__ import annotations

from typing import Tuple


Matrix3 = Tuple[
    Tuple[float, float, float],
    Tuple[float, float, float],
    Tuple[float, float, float],
]

_REFLECTION_TOLERANCE = 1e-4


def rotation_determinant(rotation: Matrix3) -> float:
    """Return the determinant of a 3-by-3 camera rotation matrix."""
    (a, b, c), (d, e, f), (g, h, i) = rotation
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def normalize_camera_rotation_handedness(rotation: Matrix3) -> tuple[Matrix3, bool]:
    """Repair Matrix-3D's known camera-local-X reflection, if present.

    ``cameras.json`` uses column-vector camera-to-world matrices. A proper
    rotation has determinant +1. The affected Matrix-3D samples instead
    contain determinant -1 because their camera-local X basis is mirrored.
    Negating that column restores a proper camera pose without moving the
    scene or changing any already-right-handed pose.
    """
    if abs(rotation_determinant(rotation) + 1.0) > _REFLECTION_TOLERANCE:
        return rotation, False

    return (
        (-rotation[0][0], rotation[0][1], rotation[0][2]),
        (-rotation[1][0], rotation[1][1], rotation[1][2]),
        (-rotation[2][0], rotation[2][1], rotation[2][2]),
    ), True
