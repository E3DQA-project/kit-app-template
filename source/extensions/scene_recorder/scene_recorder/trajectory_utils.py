"""Trajectory I/O, USD camera baking, and movie-capture integration.

Key public functions
--------------------
save_trajectory(trajectory, fps, source_scene, path)
    Serialise an in-memory trajectory list to a JSON file.

load_trajectory(path) -> dict
    Load a previously saved trajectory JSON.

bake_trajectory_to_usd(trajectory_data, stage, cam_prim_path) -> str | None
    Write time-sampled xform keyframes onto a USD Camera prim so that the
    Kit timeline can drive the camera.  Returns the prim path string on
    success.

activate_recorder_camera(stage, cam_prim_path)
    Point the active viewport at the baked camera prim.

set_timeline_range(fps, total_frames)
    Sync the Kit timeline start/end codes so Playback covers the trajectory.

open_movie_capture_window()
    Make the omni.kit.window.movie_capture panel visible so the user can
    configure output settings and start the render.

trigger_movie_capture(output_path, start_frame, end_frame, fps)
    Programmatically start a movie-capture render via the viewport capture
    interface.  Falls back gracefully when the extension is absent.

queue_viewport_frame_capture(frame_path)
    Schedule a single viewport-only PNG capture (scene render, no UI chrome).

capture_viewport_frame_sync(frame_path, update_pumps=3)
    Capture the active viewport to a file, pumping Kit updates until done.
"""
from __future__ import annotations

import datetime
import json
import os
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------

def save_trajectory(
    trajectory: List[Dict[str, Any]],
    fps: float,
    source_scene: str,
    path: str,
) -> None:
    """Write *trajectory* to *path* as a self-describing JSON file.

    Raises ``IOError`` / ``OSError`` on write failure.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    payload = {
        "version": "1.0",
        "fps": fps,
        "total_frames": len(trajectory),
        "duration_seconds": len(trajectory) / fps if fps > 0 else 0.0,
        "source_scene": source_scene,
        "recorded_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "trajectory": trajectory,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def load_trajectory(path: str) -> Dict[str, Any]:
    """Load and return a trajectory dict from *path*.

    Raises ``FileNotFoundError`` or ``ValueError`` on failure.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Trajectory file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "trajectory" not in data:
        raise ValueError(f"File does not contain a 'trajectory' key: {path}")
    return data


# ---------------------------------------------------------------------------
# USD camera baking
# ---------------------------------------------------------------------------

_RECORDER_CAM_PATH = "/RecorderCamera"


def bake_trajectory_to_usd(
    trajectory_data: Dict[str, Any],
    stage,
    cam_prim_path: str = _RECORDER_CAM_PATH,
) -> Optional[str]:
    """Create (or overwrite) a USD Camera prim at *cam_prim_path* with
    time-sampled translate + orient ops derived from *trajectory_data*.

    Returns the prim path string on success, ``None`` on failure.
    """
    try:
        from pxr import Gf, Sdf, Usd, UsdGeom

        trajectory: List[Dict[str, Any]] = trajectory_data.get("trajectory", [])
        fps: float = float(trajectory_data.get("fps", 30.0))

        if not trajectory:
            _warn("bake_trajectory_to_usd: empty trajectory, nothing to bake.")
            return None

        # Remove existing prim so we get a clean slate.
        prim_path = Sdf.Path(cam_prim_path)
        if stage.GetPrimAtPath(prim_path).IsValid():
            stage.RemovePrim(prim_path)

        usd_cam = UsdGeom.Camera.Define(stage, prim_path)
        xformable = UsdGeom.Xformable(usd_cam)

        # Add xform ops: translate then orient (no scale needed for a camera).
        translate_op = xformable.AddTranslateOp(opSuffix="recPos")
        orient_op = xformable.AddOrientOp(opSuffix="recRot")

        for fd in trajectory:
            frame: int = fd["frame"]
            time = Usd.TimeCode(frame)

            pos = fd.get("position", [0.0, 0.0, 0.0])
            translate_op.Set(Gf.Vec3d(pos[0], pos[1], pos[2]), time)

            q = fd.get("rotation_quat", [0.0, 0.0, 0.0, 1.0])
            # rotation_quat stored as [qx, qy, qz, qw]
            # UsdGeom orient op requires GfQuatf (single-precision).
            gf_quat = Gf.Quatf(float(q[3]), Gf.Vec3f(float(q[0]), float(q[1]), float(q[2])))
            orient_op.Set(gf_quat, time)

        # Copy clipping range from first matrix if available (best-effort).
        _try_set_clipping(usd_cam, trajectory[0])

        # Sync stage time metadata.
        total = len(trajectory)
        stage.SetStartTimeCode(0.0)
        stage.SetEndTimeCode(float(total - 1))
        stage.SetTimeCodesPerSecond(fps)
        stage.SetFramesPerSecond(fps)

        return cam_prim_path

    except Exception as exc:
        _warn(f"bake_trajectory_to_usd failed: {exc}")
        return None


def _try_set_clipping(usd_cam, first_frame: Dict[str, Any]) -> None:
    """Estimate a reasonable clipping range from the first frame's position magnitude."""
    try:
        from pxr import Gf
        pos = first_frame.get("position", [0.0, 0.0, 0.0])
        dist = (pos[0] ** 2 + pos[1] ** 2 + pos[2] ** 2) ** 0.5
        near = max(0.001, dist / 1000.0)
        far = max(100.0, dist * 20.0)
        usd_cam.CreateClippingRangeAttr().Set(Gf.Vec2f(near, far))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Viewport helpers
# ---------------------------------------------------------------------------

def activate_recorder_camera(stage, cam_prim_path: str = _RECORDER_CAM_PATH) -> bool:
    """Point the active viewport at *cam_prim_path*.  Returns True on success."""
    try:
        import omni.kit.viewport.utility as vpu

        vpw = vpu.get_active_viewport_window()
        if vpw is not None:
            api = getattr(vpw, "viewport_api", None)
            if api is not None and hasattr(api, "set_active_camera"):
                api.set_active_camera(cam_prim_path)
                return True

        # Fallback: older API.
        vp = getattr(vpu, "get_active_viewport", lambda: None)()
        if vp and hasattr(vp, "set_active_camera"):
            vp.set_active_camera(cam_prim_path)
            return True

        return False
    except Exception as exc:
        _warn(f"activate_recorder_camera failed: {exc}")
        return False


def set_timeline_range(fps: float, total_frames: int) -> None:
    """Set the Kit timeline to cover the entire trajectory range.

    The timeline interface works in *seconds*; time-codes-per-second is a
    stage property and is set on the stage separately in bake_trajectory_to_usd.
    """
    try:
        import omni.timeline
        tl = omni.timeline.get_timeline_interface()
        tl.set_start_time(0.0)
        end_time = (total_frames - 1) / fps if fps > 0 else 0.0
        tl.set_end_time(max(end_time, 0.0))
        tl.set_current_time(0.0)
    except Exception as exc:
        _warn(f"set_timeline_range failed: {exc}")


# ---------------------------------------------------------------------------
# Viewport-only frame capture (excludes Kit UI chrome)
# ---------------------------------------------------------------------------

def get_active_viewport_api():
    """Return the active viewport API, or None when no viewport is available."""
    try:
        import omni.kit.viewport.utility as vpu

        viewport = vpu.get_active_viewport()
        if viewport is not None:
            return viewport
        vpw = vpu.get_active_viewport_window()
        if vpw is not None:
            return getattr(vpw, "viewport_api", None)
    except Exception:
        pass
    return None


def queue_viewport_frame_capture(frame_path: str) -> bool:
    """Schedule a viewport-only PNG capture (scene render, not the full app window)."""
    viewport = get_active_viewport_api()
    if viewport is None:
        _warn("queue_viewport_frame_capture: no active viewport")
        return False
    try:
        import omni.kit.viewport.utility as vpu

        vpu.capture_viewport_to_file(viewport, file_path=frame_path)
        return True
    except Exception as exc:
        _warn(f"queue_viewport_frame_capture failed: {exc}")
        return False


def capture_viewport_frame_sync(frame_path: str, update_pumps: int = 3) -> bool:
    """Capture the active viewport to *frame_path*, pumping updates until the file exists."""
    if not queue_viewport_frame_capture(frame_path):
        return False
    try:
        import omni.kit.app

        app = omni.kit.app.get_app()
        for _ in range(max(1, update_pumps)):
            app.update()
            if os.path.isfile(frame_path):
                return True
        return os.path.isfile(frame_path)
    except Exception as exc:
        _warn(f"capture_viewport_frame_sync failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Real-time frame-sequence → video assembly
# ---------------------------------------------------------------------------

def assemble_video_from_frames(
    frames_dir: str,
    fps: float,
    output_path: str,
) -> bool:
    """Use ffmpeg to assemble a PNG sequence into a video file.

    Frames are expected to be named ``frame_NNNNNN.png`` inside *frames_dir*.
    Returns True on success, False on failure.

    ffmpeg must be on the system PATH.
    """
    import subprocess

    if not os.path.isdir(frames_dir):
        _warn(f"assemble_video_from_frames: frames directory not found: {frames_dir}")
        return False

    # Count available frames so we can report a meaningful error.
    pngs = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
    if not pngs:
        _warn(f"assemble_video_from_frames: no PNG frames found in {frames_dir}")
        return False

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    input_pattern = os.path.join(frames_dir, "frame_%06d.png")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", input_pattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
        )
        if result.returncode != 0:
            _warn(
                f"ffmpeg exited with code {result.returncode}:\n"
                + result.stderr.decode(errors="replace")
            )
            return False
        return True
    except FileNotFoundError:
        _warn(
            "assemble_video_from_frames: 'ffmpeg' not found on PATH. "
            "Install ffmpeg to enable video assembly."
        )
        return False
    except subprocess.TimeoutExpired:
        _warn("assemble_video_from_frames: ffmpeg timed out after 300 s.")
        return False
    except Exception as exc:
        _warn(f"assemble_video_from_frames: unexpected error: {exc}")
        return False


# ---------------------------------------------------------------------------
# Movie-capture integration
# ---------------------------------------------------------------------------

def open_movie_capture_window() -> bool:
    """Make the omni.kit.window.movie_capture panel visible.

    Returns True if the window was successfully shown.
    """
    try:
        import omni.kit.ui
        editor_menu = omni.kit.ui.get_editor_menu()
        if editor_menu is not None:
            # Standard menu path used by the movie-capture extension.
            editor_menu.set_value("Window/Movie Capture", True)
            return True
    except Exception:
        pass

    # Fallback: toggle via the extension's own function if available.
    try:
        import omni.kit.window.movie_capture as mc_ext
        fn = getattr(mc_ext, "show_window", None) or getattr(mc_ext, "get_instance", None)
        if fn is not None:
            result = fn()
            if hasattr(result, "show"):
                result.show()
            return True
    except Exception:
        pass

    _warn(
        "open_movie_capture_window: omni.kit.window.movie_capture is not available. "
        "Add it to the kit file dependencies."
    )
    return False


def trigger_movie_capture(
    output_path: str,
    start_frame: int,
    end_frame: int,
    fps: float,
) -> bool:
    """Programmatically start a movie-capture render.

    Tries the ``omni.kit.capture.viewport`` interface first, then falls
    back to surfacing the movie-capture window so the user can start it
    manually.

    Returns True when capture was started programmatically, False when
    the user must start it manually via the window.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # --- Attempt 1: omni.kit.capture.viewport programmatic API -----------
    try:
        import omni.kit.capture.viewport as cap

        # The public entry point varies across Kit versions; probe each name.
        get_instance = (
            getattr(cap, "get_capture_instance", None)
            or getattr(cap, "get_instance", None)
        )
        if get_instance is not None:
            inst = get_instance()
            if inst is not None:
                # Build a CaptureOptions-like object if the class exists.
                opts_cls = getattr(cap, "CaptureOptions", None)
                if opts_cls is not None:
                    opts = opts_cls()
                    opts.output_folder = os.path.dirname(output_path)
                    opts.file_name = os.path.splitext(os.path.basename(output_path))[0]
                    opts.file_type = os.path.splitext(output_path)[1].lstrip(".") or "mp4"
                    opts.start_frame = start_frame
                    opts.end_frame = end_frame
                    opts.fps = fps
                    inst.start_capture(opts)
                    return True

                # Fallback: older API with keyword arguments.
                start_fn = getattr(inst, "start_capture", None) or getattr(inst, "start", None)
                if start_fn is not None:
                    start_fn(
                        output_path=output_path,
                        start_frame=start_frame,
                        end_frame=end_frame,
                        fps=fps,
                    )
                    return True

    except Exception as exc:
        _warn(f"trigger_movie_capture via capture.viewport failed: {exc}")

    # --- Attempt 2: surface the movie-capture window ---------------------
    opened = open_movie_capture_window()
    if opened:
        _warn(
            "Programmatic capture unavailable. "
            "Configure output settings in the Movie Capture window and click Record."
        )
    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _warn(msg: str) -> None:
    try:
        import omni.log
        omni.log.warn(f"[scene_recorder] {msg}")
    except Exception:
        print(f"[scene_recorder] WARN: {msg}")
