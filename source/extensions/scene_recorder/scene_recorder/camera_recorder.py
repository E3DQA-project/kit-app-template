"""Live camera pose recorder.

Subscribes to the Kit update event stream and samples the active viewport
camera transform at a configurable rate.  All frames are stored in memory
and can be retrieved as a trajectory list when recording stops.

Optionally queues a viewport frame capture on every sampled tick so that
a PNG sequence is written alongside the trajectory, ready for ffmpeg assembly.
"""
from __future__ import annotations

import math
import os
from typing import Any, Callable, Dict, List, Optional

from . import trajectory_utils as tutils


class CameraRecorder:
    """Poll the active viewport camera pose and accumulate a trajectory.

    Parameters
    ----------
    sample_fps:
        How many camera poses (and optional video frames) to capture per second.
    capture_video:
        When True, also queue a viewport screenshot on every sampled tick.
    frames_dir:
        Directory where PNG frames are written when *capture_video* is True.
        Defaults to a ``_frames`` sub-folder next to the JSON output path.

    Usage::

        recorder = CameraRecorder(sample_fps=30, capture_video=True, frames_dir="/tmp/frames")
        recorder.start(on_frame_cb=lambda n: ...)
        # ... user navigates ...
        trajectory, frame_paths = recorder.stop()
    """

    def __init__(
        self,
        sample_fps: float = 30.0,
        capture_video: bool = False,
        frames_dir: str = "",
    ) -> None:
        # Configurable by user
        self.sample_fps: float = max(1.0, sample_fps)
        self.capture_video: bool = capture_video
        self.frames_dir: str = frames_dir

        # Internal states
        self._trajectory: List[Dict[str, Any]] = []
        self._frame_paths: List[str] = []
        self._update_sub = None
        self._elapsed: float = 0.0
        self._frame_idx: int = 0
        self._on_frame_cb: Optional[Callable[[int], None]] = None
        self._recording: bool = False
        self._viewport_capture_enabled: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def frame_count(self) -> int:
        return len(self._trajectory)

    def start(self, on_frame_cb: Optional[Callable[[int], None]] = None) -> None:
        """Begin recording.  *on_frame_cb* is called with the frame count after each sample."""
        """
        This line tells Python (and type checkers like Mypy) exactly what inputs the method expects and what it returns.

            - on_frame_cb: This is the name of the argument. It stands for "on frame callback".

            - Callable[[int], None]: This means the argument must be a function.

            - [int] part means this function must accept exactly one integer as an argument (in this case, the frame count).

            - , None part means this function shouldn't return anything.

            - Optional[...]: This means the argument can either be the function we just described, or it can be None.

            - = None: This sets the default value. If you call start(), it will default to None.

            - -> None: This means the start method itself doesn't return any value.
        """
        if self._recording:
            return
        self._trajectory = []
        self._frame_paths = []
        self._elapsed = 0.0
        self._frame_idx = 0
        self._on_frame_cb = on_frame_cb
        self._recording = True

        if self.capture_video:
            self._ensure_frames_dir()
            self._prepare_viewport_capture()

        self._subscribe_update()

    def stop(self):
        """Stop recording.

        Returns
        -------
        tuple[list, list]
            ``(trajectory, frame_paths)`` where *frame_paths* is the ordered
            list of PNG paths written during recording (empty if
            *capture_video* was False).
        """
        import omni.log
        if not self._recording:
            omni.log.warn(f"[scene_rewcorder] Not recording")
            omni.log.warn(f"[scene_recorder] Trajectory: {self._trajectory}")
            omni.log.warn(f"[scene_recorder] Frame paths: {self._frame_paths}")
            return list(self._trajectory), list(self._frame_paths)
        self._recording = False
        self._unsubscribe_update()
        omni.log.warn(f"[scene_recorder] Stopped recording")
        omni.log.warn(f"[scene_recorder] Trajectory: {self._trajectory}")
        omni.log.warn(f"[scene_recorder] Frame paths: {self._frame_paths}")
        return list(self._trajectory), list(self._frame_paths)

    def discard(self) -> None:
        """Stop recording without returning data."""
        self._recording = False
        self._unsubscribe_update()
        self._trajectory = []
        self._frame_paths = []

    # ------------------------------------------------------------------
    # Update subscription
    # ------------------------------------------------------------------

    def _subscribe_update(self) -> None:
        try:
            import omni.kit.app
            self._update_sub = (
                omni.kit.app.get_app()  # Grabs the core instance of the running Omniverse application engine.
                .get_update_event_stream()  # Accesses the application's "heartbeat" stream. This stream fires an event every single time the app updates its state or renders a new frame (usually 60+ times a second).
                .create_subscription_to_pop(self._on_update, name="scene_recorder_poll")  # This is where the magic happens. It registers a listener (a subscription) onto that heartbeat stream. Whenever the stream fires an event, the _on_update method will be called.
            )
        except Exception as exc:
            import omni.log
            omni.log.warn(f"[scene_recorder] Could not subscribe to update stream: {exc}")

    def _unsubscribe_update(self) -> None:
        self._update_sub = None

    # ------------------------------------------------------------------
    # Per-frame logic
    # ------------------------------------------------------------------

    def _on_update(self, event) -> None:
        if not self._recording:
            return

        dt: float = event.payload.get("dt", 0.0) if event.payload else 0.0
        self._elapsed += dt

        interval = 1.0 / self.sample_fps
        if self._elapsed < interval and self._frame_idx > 0:
            return

        # Consume one interval's worth of elapsed time to avoid drift.
        if self._frame_idx > 0:
            self._elapsed -= interval

        pose = _read_camera_pose()
        if pose is None:
            return

        frame_data: Dict[str, Any] = {
            "frame": self._frame_idx,
            "timestamp": self._frame_idx / self.sample_fps,
            **pose,
        }
        self._trajectory.append(frame_data)

        if self.capture_video:
            self._queue_frame_capture(self._frame_idx)

        self._frame_idx += 1

        if self._on_frame_cb is not None:
            try:
                self._on_frame_cb(self._frame_idx)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Frame-capture helpers
    # ------------------------------------------------------------------

    def _ensure_frames_dir(self) -> None:
        d = self.frames_dir
        # If the frames directory is not set, use the default directory of /home/pierce/scene_recorder_frames
        if not d:
            d = os.path.join(os.path.expanduser("~"), "scene_recorder_frames")
            self.frames_dir = d
        os.makedirs(d, exist_ok=True)

    def _prepare_viewport_capture(self) -> None:
        viewport = tutils.get_active_viewport_api()
        if viewport is None:
            import omni.log
            omni.log.warn(
                "[scene_recorder] No active viewport; video frames will not be saved"
            )
            self._viewport_capture_enabled = False
            return
        self._viewport_capture_enabled = True

    def _queue_frame_capture(self, frame_idx: int) -> None:
        if not self._viewport_capture_enabled:
            return
        frame_path = os.path.join(self.frames_dir, f"frame_{frame_idx:06d}.png")
        if tutils.queue_viewport_frame_capture(frame_path):
            self._frame_paths.append(frame_path)


# ---------------------------------------------------------------------------
# Camera pose helpers
# ---------------------------------------------------------------------------

def _read_camera_pose() -> Optional[Dict[str, Any]]:
    """Return the world-space pose of the active viewport camera, or None."""
    try:
        import omni.kit.viewport.utility as vpu
        import omni.usd
        from pxr import Gf, Usd, UsdGeom

        vpw = vpu.get_active_viewport_window()
        if vpw is None:
            return None
        api = getattr(vpw, "viewport_api", None)
        if api is None:
            return None

        cam_path = getattr(api, "camera_path", None)
        if not cam_path:
            return None

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return None

        cam_prim = stage.GetPrimAtPath(cam_path)
        if not cam_prim.IsValid():
            return None

        xformable = UsdGeom.Xformable(cam_prim)
        time = Usd.TimeCode.Default()
        mat: Gf.Matrix4d = xformable.ComputeLocalToWorldTransform(time)

        # Translation
        t = mat.ExtractTranslation()
        pos = [t[0], t[1], t[2]]

        # Rotation as quaternion (Gf.Rotation → Gf.Quatd)
        rot3 = mat.ExtractRotation()
        q = rot3.GetQuat()
        qi = q.GetImaginary()
        quat = [qi[0], qi[1], qi[2], q.GetReal()]  # [qx, qy, qz, qw]

        # Rotation as Euler angles (degrees, XYZ order via decompose)
        euler = _quat_to_euler_deg(quat)

        # Full 4x4 matrix (row-major list-of-lists)
        matrix = [[mat[r][c] for c in range(4)] for r in range(4)]

        return {
            "position": pos,
            "rotation_euler_deg": euler,
            "rotation_quat": quat,
            "transform_matrix_4x4": matrix,
        }

    except Exception as exc:
        try:
            import omni.log
            omni.log.warn(f"[scene_recorder] Camera pose read failed: {exc}")
        except Exception:
            pass
        return None


def _quat_to_euler_deg(quat: List[float]) -> List[float]:
    """Convert [qx, qy, qz, qw] to Euler angles [rx, ry, rz] in degrees (XYZ extrinsic)."""
    qx, qy, qz, qw = quat

    # Roll (X)
    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (Y)
    sinp = 2.0 * (qw * qy - qz * qx)
    pitch = math.copysign(math.pi / 2.0, sinp) if abs(sinp) >= 1.0 else math.asin(sinp)

    # Yaw (Z)
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return [math.degrees(roll), math.degrees(pitch), math.degrees(yaw)]
