"""Dataset camera conventions shared by the E3DQA and MOS viewers."""

from dataclasses import dataclass


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
