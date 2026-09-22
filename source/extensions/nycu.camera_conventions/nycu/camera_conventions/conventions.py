"""Dataset camera conventions shared by the E3DQA and MOS viewers."""

from dataclasses import dataclass
from typing import Tuple


Matrix3 = Tuple[
    Tuple[float, float, float],
    Tuple[float, float, float],
    Tuple[float, float, float],
]

_REFLECTION_TOLERANCE = 1e-4


@dataclass(frozen=True)
class CameraConvention:
    """Coordinate conversion options for one dataset-generation method."""

    method: str
    scene_orientation: str
    force_z_up: bool
    rotation_is_world_to_camera: bool
    opencv_axes: bool
    swap_yz: bool
    camera_roll_degrees: int
    stage_up_axis: str


_CONVENTIONS = {
    # Matrix-3D USDZ exports are already Z-up. Its cameras.json rotations are
    # camera-to-world poses in the native USD camera convention.
    "matrix3d": CameraConvention(
        method="matrix3d",
        scene_orientation="none",
        force_z_up=True,
        rotation_is_world_to_camera=False,
        opencv_axes=False,
        swap_yz=False,
        camera_roll_degrees=180,
        # Matrix-3D camera poses use -Z forward and +Y image-down. Kit's
        # navigation frame therefore needs Y-up; the USDZ metadata's Z-up
        # declaration describes the exported volume, not the interaction basis.
        stage_up_axis="y",
    ),
}


def get_camera_convention(method: str) -> CameraConvention:
    """Return the convention for *method*, rejecting unknown methods early."""
    key = (method or "").strip().lower().replace("-", "").replace("_", "")
    try:
        return _CONVENTIONS[key]
    except KeyError as exc:
        known = ", ".join(sorted(_CONVENTIONS))
        raise ValueError(f"Unknown camera method {method!r}; expected one of: {known}") from exc


def rotation_determinant(rotation: Matrix3) -> float:
    """Return the determinant of a 3-by-3 camera rotation matrix."""
    (a, b, c), (d, e, f), (g, h, i) = rotation
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def normalize_camera_rotation_handedness(rotation: Matrix3) -> tuple[Matrix3, bool]:
    """Repair Matrix-3D's known reflected camera-local X basis only."""
    if abs(rotation_determinant(rotation) + 1.0) > _REFLECTION_TOLERANCE:
        return rotation, False

    return (
        (-rotation[0][0], rotation[0][1], rotation[0][2]),
        (-rotation[1][0], rotation[1][1], rotation[1][2]),
        (-rotation[2][0], rotation[2][1], rotation[2][2]),
    ), True
