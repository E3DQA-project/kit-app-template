"""
MOS App Extension  –  nycu.mos_app_extension

Orchestrates the MOS evaluation workflow:
  1. Participant name prompt (blocking until confirmed).
  2. Ordered USDZ scene list loaded from a JSON file.
  3. Camera initialisation from cameras.json (usdz_folder_browser convention).
  4. R = reset camera to initial post-load pose.
  5. Enter = open scoring panel / Esc = close without submitting.
  6. "Next" saves five ordinal metric scores and advances to the next scene.
  7. Scores appended (never overwritten) to a per-participant JSON file.

Keyboard shortcuts (active after name is confirmed):
  R      – reset camera to initial spot (scoring panel closed)
  Enter  – open scoring panel
  Esc    – close scoring panel
"""

from __future__ import annotations

import asyncio
import gc
import json
import os
from datetime import datetime, timezone
from math import sqrt
from typing import Any, Dict, List, Optional, Tuple

import carb
import carb.input
import carb.settings
import carb.tokens
import omni.ext
import omni.kit.app
import omni.kit.commands
import omni.log
import omni.ui as ui
import omni.usd

from .load_diagnostics import (
    _DeferredGenerationGate,
    _FrameStabilityGate,
    _LoadDiagnostics,
    _ReadinessGate,
    _RendererPhaseGate,
)
from .ui_theme import (
    PARTICIPANT_ACCENT,
    TEXT_HINT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    modal_frame_style,
    modal_window_flags,
    primary_button_style,
    slider_style,
    text_field_style,
)
from nycu.camera_conventions import (
    get_camera_convention,
    normalize_camera_rotation_handedness,
    rotation_determinant,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_EXT_ID = "nycu.mos_app_extension"

_SLIDER_STEPS = ["Very poor", "Poor", "Average", "Good", "Very good"]

_METRICS: List[Tuple[str, str]] = [
    ("texture_fidelity",              "Texture fidelity"),
    ("semantic_contextual_coherence", "Semantic & contextual coherence"),
    ("geometric_consistency",         "Geometric consistency"),
    ("volumetric_cleanliness",        "Volumetric cleanliness"),
    ("overall_quality",               "Overall quality"),
]

# Scene/camera convention selected by the dataset-generation method. Matrix-3D
# USDZ exports are already native Z-up, so no additional scene rotation is
# applied. Other methods can be added to the shared convention module later.
_CAMERA_METHOD = "matrix3d"
_CAMERA_CONVENTION = get_camera_convention(_CAMERA_METHOD)
_ORIENT_PRESET = _CAMERA_CONVENTION.scene_orientation
_FORCE_Z_UP    = _CAMERA_CONVENTION.force_z_up

# cameras.json walk-up search patterns (same defaults as usdz_folder_browser).
_CAM_PATTERNS = [
    "geom_optim/output/cameras.json",
    "cameras.json",
]

# carb.settings paths for camera/navigation (mirror camera_controls).
_S_CAM_VELOCITY = "/persistent/app/viewport/camMoveVelocity"
_S_CAM_VEL_MIN  = "/persistent/app/viewport/camVelocityMin"
_S_CAM_VEL_MAX  = "/persistent/app/viewport/camVelocityMax"
_S_TOOL         = "/app/viewport/currentTool"
_S_ACTIVE_OP    = "/exts/omni.kit.viewport.navigation.core/activeOperation"
_S_DEFAULT_OP   = "/exts/omni.kit.viewport.navigation.camera_manipulator/defaultOperation"
_S_CONTEXT_MENU = "/exts/omni.kit.window.viewport/showContextMenu"
_S_LOOK_SPEED_X = "/persistent/exts/omni.kit.manipulator.camera/lookSpeed/0"

# Status overlay (top-right HUD).
_STATUS_FONT_SIZE = 18
_STATUS_MARGIN    = 16
_STATUS_HPAD      = 24
_STATUS_MIN_WIDTH = 280
_STATUS_MAX_WIDTH = 960
_STATUS_HEIGHT    = 36

# Diagnostic-only viewport sampling.  This estimates when the displayed image
# stops changing; it does not prove that the new scene is the image on screen.
_STABILITY_CAPTURE_COUNT = 4
_STABILITY_CAPTURE_GAP_UPDATES = 15
_STABILITY_REQUIRED_CONSECUTIVE = 2
_STABILITY_MAX_MEAN_DELTA = 3
_STABILITY_SIGNATURE_SAMPLES = 2048

# Participant prompt dialog.
_PROMPT_WIN_WIDTH  = 560
_PROMPT_WIN_HEIGHT = 220
_PROMPT_FONT_SIZE  = 20
_PROMPT_LABEL_W    = 72
_PROMPT_FIELD_H    = 38
_PROMPT_BTN_W      = 180
_PROMPT_BTN_H      = 44

# Scoring panel.
_SCORE_WIN_WIDTH   = 760
_SCORE_WIN_HEIGHT  = 540
_SCORE_FONT_SIZE   = 22
_SCORE_HEADER_SIZE = 22
_SCORE_FOOTER_SIZE = 16
_SCORE_ROW_H       = 44
_SCORE_LABEL_W     = 360
_SCORE_SLIDER_W    = 180
_SCORE_SLIDER_H    = 28
_SCORE_VALUE_W     = 36
_SCORE_STEP_W      = 130
_SCORE_BTN_W       = 180
_SCORE_BTN_H       = 48

_SLIDER_STYLE = {**slider_style(),
    "draw_mode": ui.SliderDrawMode.HANDLE,
}


# ── State machine ──────────────────────────────────────────────────────────────

class _St:
    PROMPT     = "prompt"
    LOADING    = "loading"
    NAVIGATING = "navigating"
    SCORING    = "scoring"
    DONE       = "done"


# ── Score storage helpers ──────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scores_dir() -> str:
    # 1. Resolve via carb tokens — works at runtime in the build/install tree,
    #    puts scores next to mos_scenes.json in <build>/data/scores/.
    try:
        import carb.tokens as _ct
        resolved = _ct.get_tokens_interface().resolve("${app}/../data/scores")
        if resolved and not resolved.startswith("${"):
            return resolved
    except Exception:
        pass

    # 2. Source-tree fallback — go up 4 levels from this file's directory
    #    (.../source/extensions/nycu.mos_app_extension/nycu/mos_app_extension)
    #    to reach .../source/, then into data/scores.
    return os.path.normpath(os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "..",
        "data", "scores",
    ))


def _score_file(participant: str) -> str:
    safe = "".join(
        c if (c.isalnum() or c in "- _") else "_" for c in participant
    ).strip() or "unknown"
    return os.path.join(_scores_dir(), f"{safe}.json")


def _normalize_scene_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _load_scored_scene_paths(participant: str) -> set[str]:
    """Return normalized scene paths already scored for this participant."""
    data = _read_json(_score_file(participant))
    if not isinstance(data, dict):
        return set()

    scored: set[str] = set()
    for session in data.get("sessions", []):
        if not isinstance(session, dict):
            continue
        scene_path = session.get("scene_path")
        if isinstance(scene_path, str) and scene_path:
            scored.add(_normalize_scene_path(scene_path))
    return scored


def _filter_unscored_scenes(
    scenes: List[str], participant: str
) -> Tuple[List[str], int]:
    """Drop scenes that already appear in the participant's score file."""
    scored = _load_scored_scene_paths(participant)
    if not scored:
        return scenes, 0

    kept: List[str] = []
    skipped = 0
    for scene in scenes:
        if _normalize_scene_path(scene) in scored:
            skipped += 1
        else:
            kept.append(scene)
    return kept, skipped


def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=False)
    os.replace(tmp, path)


# ── Scene-list loading ─────────────────────────────────────────────────────────

def _load_scene_list(json_path: str) -> List[str]:
    """Return a flat ordered list of absolute .usdz paths.

    Supports two JSON formats:

    Format A (PRD):
        {"version": 1, "scenes": ["/abs/path/a.usdz", ...]}

    Format B (usdz_file_list.json example):
        [{"session": 1, "filepaths": ["/abs/path/a.usdz", ...]}, ...]
    """
    data = _read_json(json_path)
    if data is None:
        raise FileNotFoundError(f"Cannot open scene list: {json_path}")

    raw: List[str] = []
    if isinstance(data, dict) and "scenes" in data:
        # Format A
        for p in data.get("scenes", []):
            if isinstance(p, str):
                raw.append(p)
    elif isinstance(data, list):
        # Format B
        for session in data:
            if isinstance(session, dict):
                for p in session.get("filepaths", []):
                    if isinstance(p, str):
                        raw.append(p)
    else:
        raise ValueError("Unrecognised scene-list JSON format.")

    base = os.path.dirname(os.path.abspath(json_path))
    resolved: List[str] = []
    for p in raw:
        if not p.lower().endswith(".usdz"):
            omni.log.warn(f"[{_EXT_ID}] Skipping non-.usdz entry: {p}")
            continue
        if not os.path.isabs(p):
            p = os.path.normpath(os.path.join(base, p))
        resolved.append(_normalize_scene_path(p))
    return resolved


# ── Stage helpers (adapted from usdz_folder_browser) ──────────────────────────

def _unload_stage() -> None:
    try:
        omni.usd.get_context().close_stage()
    except Exception:
        pass
    try:
        ctx = omni.usd.get_context()
        if hasattr(ctx, "new_stage"):
            ctx.new_stage()
    except Exception:
        pass
    try:
        for cmd in ("CreateNewStage", "NewStage"):
            try:
                omni.kit.commands.execute(cmd)
                break
            except Exception:
                continue
    except Exception:
        pass
    try:
        gc.collect()
    except Exception:
        pass


def _resolve_cameras_json(scene_path: str) -> Optional[str]:
    cur = os.path.abspath(os.path.dirname(scene_path))
    prev = None
    while cur and cur != prev:
        for pattern in _CAM_PATTERNS:
            parts = pattern.replace("\\", "/").split("/")
            candidate = os.path.normpath(os.path.join(cur, *parts))
            if os.path.isfile(candidate):
                omni.log.info(f"[{_EXT_ID}] Found cameras.json: {candidate}")
                return candidate
        prev = cur
        cur = os.path.dirname(cur)
    return None


def _load_camera0(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
    except Exception:
        pass
    return None


# ── Matrix helpers ─────────────────────────────────────────────────────────────

def _mat3(m: Any) -> Optional[Tuple]:
    try:
        if not (isinstance(m, list) and len(m) == 3):
            return None
        rows = []
        for r in m:
            if not (isinstance(r, list) and len(r) == 3):
                return None
            rows.append((float(r[0]), float(r[1]), float(r[2])))
        return tuple(rows)
    except Exception:
        return None


def _vec3(v: Any) -> Optional[Tuple[float, float, float]]:
    try:
        if not (isinstance(v, list) and len(v) == 3):
            return None
        return (float(v[0]), float(v[1]), float(v[2]))
    except Exception:
        return None


def _T(m):
    return (
        (m[0][0], m[1][0], m[2][0]),
        (m[0][1], m[1][1], m[2][1]),
        (m[0][2], m[1][2], m[2][2]),
    )


def _mm(a, b):
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )


def _mv(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


# ── USD scene helpers ──────────────────────────────────────────────────────────

def _scene_preset_rot3(preset: str):
    try:
        from pxr import Gf

        p = (preset or "none").lower()
        if p == "none":
            return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        axis_map = {
            "rx+90": (Gf.Vec3d(1, 0, 0),  90.0),
            "rx-90": (Gf.Vec3d(1, 0, 0), -90.0),
            "ry+90": (Gf.Vec3d(0, 1, 0),  90.0),
            "ry-90": (Gf.Vec3d(0, 1, 0), -90.0),
            "rz+90": (Gf.Vec3d(0, 0, 1),  90.0),
            "rz-90": (Gf.Vec3d(0, 0, 1), -90.0),
            "rz+180": (Gf.Vec3d(0, 0, 1), 180.0),
            "rz-180": (Gf.Vec3d(0, 0, 1), -180.0),
        }
        if p not in axis_map:
            return None
        axis, angle = axis_map[p]
        m = Gf.Matrix4d().SetRotate(Gf.Rotation(axis, angle))
        return (
            (m[0][0], m[0][1], m[0][2]),
            (m[1][0], m[1][1], m[1][2]),
            (m[2][0], m[2][1], m[2][2]),
        )
    except Exception:
        return None


def _camera_roll_rot3():
    degrees = _CAMERA_CONVENTION.camera_roll_degrees
    if not degrees:
        return None
    sign = "+" if degrees > 0 else "-"
    return _scene_preset_rot3(f"rz{sign}{abs(degrees):g}")


def _apply_orientation(preset: str, force_z_up: bool, stage_up_axis: str = "") -> bool:
    try:
        from pxr import Gf, Sdf, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return False
        axis = (stage_up_axis or ("z" if force_z_up else "")).lower()
        if axis in ("y", "z"):
            try:
                UsdGeom.SetStageUpAxis(stage, getattr(UsdGeom.Tokens, axis))
            except Exception:
                pass
        p = (preset or "none").lower()
        if p == "none":
            return True
        m3 = _scene_preset_rot3(p)
        if m3 is None:
            return False
        m = Gf.Matrix4d(
            m3[0][0], m3[0][1], m3[0][2], 0.0,
            m3[1][0], m3[1][1], m3[1][2], 0.0,
            m3[2][0], m3[2][1], m3[2][2], 0.0,
            0.0, 0.0, 0.0, 1.0,
        )
        root = stage.GetPrimAtPath(Sdf.Path("/World"))
        if not root or not root.IsValid():
            for child in stage.GetPseudoRoot().GetChildren():
                if child and child.IsValid():
                    root = child
                    break
        if not root or not root.IsValid():
            return False
        xf = UsdGeom.Xformable(root)
        ops = xf.GetOrderedXformOps()
        if ops:
            try:
                ops[0].Set(m)
            except Exception:
                xf.ClearXformOpOrder()
                xf.AddTransformOp().Set(m)
        else:
            xf.AddTransformOp().Set(m)
        return True
    except Exception as exc:
        omni.log.warn(f"[{_EXT_ID}] _apply_orientation error: {exc}")
        return False


def _apply_camera_from_json(cam: Dict[str, Any], scene_preset: str) -> bool:
    """Place /BrowserCamera using a cameras.json camera-0 dict.

    Axis convention matches usdz_folder_browser._on_load defaults:
      rot_is_w2c = False, cv_axes = False, swap_yz = False.
    Only the scene-orientation preset rotation is baked into the pose.
    """
    pos = _vec3(cam.get("position"))
    rot = _mat3(cam.get("rotation"))
    if pos is None or rot is None:
        return False
    try:
        from pxr import Gf, Sdf, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return False

        r, p = rot, pos
        original_determinant = rotation_determinant(r)
        r, repaired_reflection = normalize_camera_rotation_handedness(r)
        if repaired_reflection:
            omni.log.warn(
                f"[{_EXT_ID}] CAMERA_HANDEDNESS_REPAIRED "
                f"determinant={original_determinant:.6f} "
                "correction=camera_local_x_reflection"
            )
        elif abs(original_determinant - 1.0) > 1e-4:
            omni.log.warn(
                f"[{_EXT_ID}] CAMERA_HANDEDNESS_UNCHANGED "
                f"determinant={original_determinant:.6f}; "
                "expected a proper rotation (+1) or the known Matrix-3D reflection (-1)"
            )
        # Bake scene-orientation rotation into the camera pose so it aligns
        # with the rotated /World content (same logic as usdz_folder_browser).
        pr = _scene_preset_rot3(scene_preset)
        if pr is not None and scene_preset != "none":
            r = _mm(pr, r)
            p = _mv(pr, p)

        # Matrix-3D preserves the expected forward direction but its image-up
        # basis is inverted for the viewport camera. Roll locally so forward,
        # position, and scene coordinates remain unchanged.
        roll = _camera_roll_rot3()
        if roll is not None:
            r = _mm(r, roll)

        # cameras.json stores a column-vector camera-to-world pose. USD's
        # Gf.Matrix4d uses the equivalent row-vector representation, so the
        # rotation must be transposed only at this serialization boundary.
        r0, r1, r2 = r
        xform = Gf.Matrix4d(
            r0[0], r1[0], r2[0], 0.0,
            r0[1], r1[1], r2[1], 0.0,
            r0[2], r1[2], r2[2], 0.0,
            p[0],  p[1],  p[2],  1.0,
        )

        cam_path = Sdf.Path("/BrowserCamera")
        prim = stage.GetPrimAtPath(cam_path)
        if not prim or not prim.IsValid():
            prim = stage.DefinePrim(cam_path, "Camera")

        xf = UsdGeom.Xformable(prim)
        ops = xf.GetOrderedXformOps()
        if ops:
            try:
                ops[0].Set(xform)
            except Exception:
                xf.ClearXformOpOrder()
                xf.AddTransformOp().Set(xform)
        else:
            xf.AddTransformOp().Set(xform)

        usd_cam = UsdGeom.Camera(prim)
        w  = float(cam.get("width")  or 1024)
        h  = float(cam.get("height") or 1024)
        fx = cam.get("fx")
        fy = cam.get("fy")
        horiz_ap = 20.955
        vert_ap  = horiz_ap * h / w if w > 0 else 15.29
        try:
            usd_cam.CreateHorizontalApertureAttr().Set(horiz_ap)
            usd_cam.CreateVerticalApertureAttr().Set(vert_ap)
            if fx is not None and w > 0:
                usd_cam.CreateFocalLengthAttr().Set(float(fx) * horiz_ap / w)
            elif fy is not None and h > 0:
                usd_cam.CreateFocalLengthAttr().Set(float(fy) * vert_ap / h)
        except Exception:
            pass
        try:
            dist = sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2)
            usd_cam.CreateClippingRangeAttr().Set(
                Gf.Vec2f(max(0.001, dist / 1000.0), max(100.0, dist * 20.0))
            )
        except Exception:
            pass

        # Activate in viewport
        try:
            import omni.kit.viewport.utility as vpu
            vp = getattr(vpu, "get_active_viewport", lambda: None)()
            if vp and hasattr(vp, "set_active_camera"):
                vp.set_active_camera(str(cam_path))
            else:
                vpw = getattr(vpu, "get_active_viewport_window", lambda: None)()
                if vpw:
                    api = getattr(vpw, "viewport_api", None)
                    if api and hasattr(api, "set_active_camera"):
                        api.set_active_camera(str(cam_path))
        except Exception:
            pass

        return True
    except Exception as exc:
        omni.log.warn(f"[{_EXT_ID}] _apply_camera_from_json error: {exc}")
        return False


# ── Extension ──────────────────────────────────────────────────────────────────

class MosAppExtension(omni.ext.IExt):

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_startup(self, _ext_id: str) -> None:
        self._state: str = _St.PROMPT
        self._participant: str = ""
        self._scenes: List[str] = []
        self._index: int = 0
        self._initial_cam_xform = None  # GfMatrix4d of /BrowserCamera after load

        self._stage_sub = None
        self._pending_abs_path: Optional[str] = None
        self._render_sub = None
        self._renderer_subs: List[Any] = []
        self._load_generation = 0
        self._load_diag: Optional[_LoadDiagnostics] = None
        self._readiness_gate: Optional[_ReadinessGate] = None
        self._renderer_phase_gate: Optional[_RendererPhaseGate] = None
        self._user_action_gate: Optional[_ReadinessGate] = None
        self._frame_stability_gate: Optional[_FrameStabilityGate] = None
        self._stability_start_gate = _DeferredGenerationGate()
        self._stability_start_sub = (
            omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
                self._on_stability_start_update, name="mos_app_stability_start"
            )
        )
        self._capture_task: Optional[asyncio.Task] = None
        self._capture_baseline: Optional[Tuple[int, ...]] = None
        self._capture_previous: Optional[Tuple[int, ...]] = None
        self._capture_sample_count = 0

        # UI
        self._prompt_win: Optional[ui.Window] = None
        self._status_win: Optional[ui.Window] = None
        self._scoring_win: Optional[ui.Window] = None
        self._name_model: Optional[ui.SimpleStringModel] = None
        self._continue_btn: Optional[ui.Button] = None
        self._status_lbl: Optional[ui.Label] = None
        self._score_models: Dict[str, ui.SimpleIntModel] = {}
        self._score_step_labels: Dict[str, ui.Label] = {}
        self._score_value_labels: Dict[str, ui.Label] = {}
        self._scene_info_lbl: Optional[ui.Label] = None
        self._scoring_hint_lbl: Optional[ui.Label] = None

        # Keyboard
        self._carb_input = None
        self._kbd_device = None
        self._kbd_sub = None
        self._mouse_device = None
        self._mouse_sub = None
        self._register_keyboard()

        # Camera / nav defaults
        self._apply_nav_defaults()

        # Show participant prompt after the app settles
        asyncio.ensure_future(self._deferred_start())

    def on_shutdown(self) -> None:
        self._unregister_keyboard()
        self._stage_sub = None
        self._render_sub = None
        self._renderer_subs = []
        self._load_diag = None
        self._readiness_gate = None
        self._renderer_phase_gate = None
        self._user_action_gate = None
        self._frame_stability_gate = None
        self._stability_start_sub = None
        self._capture_task = None
        self._stability_start_gate.clear()
        self._capture_baseline = None
        self._capture_previous = None
        self._prompt_win = None
        self._status_win = None
        self._scoring_win = None
        self._name_model = None
        self._continue_btn = None
        self._status_lbl = None
        self._score_models = {}
        self._score_step_labels = {}
        self._score_value_labels = {}
        self._scene_info_lbl = None
        self._scoring_hint_lbl = None

    # ── Nav defaults ───────────────────────────────────────────────────────────

    def _apply_nav_defaults(self) -> None:
        """Mirror camera_controls._apply_defaults so WASD / gamepad left-stick move."""
        try:
            s = carb.settings.get_settings()

            # Ensure move velocity is at least 1.0 (same logic as camera_controls).
            try:
                current_vel = float(s.get_as_float(_S_CAM_VELOCITY) or 0.0)
            except Exception:
                current_vel = 0.0
            s.set(_S_CAM_VELOCITY, max(1.0, current_vel))

            # Speed bounds.
            s.set(_S_CAM_VEL_MIN, 0.01)
            try:
                current_max = float(s.get_as_float(_S_CAM_VEL_MAX) or 0.0)
            except Exception:
                current_max = 0.0
            s.set(_S_CAM_VEL_MAX, max(50.0, current_max))

            # Fly-mode navigation.
            s.set(_S_TOOL, "navigation")
            s.set(_S_ACTIVE_OP, "fly")
            s.set(_S_DEFAULT_OP, "fly")
            current_look_x = float(s.get_as_float(_S_LOOK_SPEED_X) or 180.0)
            s.set(_S_LOOK_SPEED_X, -abs(current_look_x or 180.0))

            # Disable RMB context menu so RMB can be used for look.
            s.set(_S_CONTEXT_MENU, False)
        except Exception:
            pass

    # ── Keyboard ───────────────────────────────────────────────────────────────

    def _register_keyboard(self) -> None:
        try:
            import omni.appwindow
            self._carb_input = carb.input.acquire_input_interface()
            app_window = omni.appwindow.get_default_app_window()
            if app_window is None:
                raise RuntimeError("No default app window available yet.")
            self._kbd_device = app_window.get_keyboard()
            self._kbd_sub = self._carb_input.subscribe_to_keyboard_events(
                self._kbd_device, self._on_key
            )
            self._mouse_device = app_window.get_mouse()
            self._mouse_sub = self._carb_input.subscribe_to_mouse_events(
                self._mouse_device, self._on_mouse
            )
            omni.log.info(f"[{_EXT_ID}] Keyboard and mouse subscribed.")
        except Exception as exc:
            omni.log.warn(
                f"[{_EXT_ID}] Keyboard subscribe failed: {exc} "
                "(will retry after window is ready)"
            )
            # Schedule a retry — the app window may not exist yet at startup.
            asyncio.ensure_future(self._retry_keyboard())

    async def _retry_keyboard(self) -> None:
        app = omni.kit.app.get_app()
        for attempt in range(30):
            await app.next_update_async()
            try:
                import omni.appwindow
                self._carb_input = carb.input.acquire_input_interface()
                app_window = omni.appwindow.get_default_app_window()
                if app_window is None:
                    continue
                self._kbd_device = app_window.get_keyboard()
                self._kbd_sub = self._carb_input.subscribe_to_keyboard_events(
                    self._kbd_device, self._on_key
                )
                self._mouse_device = app_window.get_mouse()
                self._mouse_sub = self._carb_input.subscribe_to_mouse_events(
                    self._mouse_device, self._on_mouse
                )
                omni.log.info(
                    f"[{_EXT_ID}] Keyboard and mouse subscribed (attempt {attempt + 1})."
                )
                return
            except Exception:
                continue
        omni.log.warn(f"[{_EXT_ID}] Keyboard subscription permanently failed.")

    def _unregister_keyboard(self) -> None:
        try:
            if self._carb_input and self._kbd_device and self._kbd_sub is not None:
                self._carb_input.unsubscribe_to_keyboard_events(
                    self._kbd_device, self._kbd_sub
                )
        except Exception:
            pass
        try:
            if self._carb_input and self._mouse_device and self._mouse_sub is not None:
                self._carb_input.unsubscribe_to_mouse_events(
                    self._mouse_device, self._mouse_sub
                )
        except Exception:
            pass
        self._kbd_sub = None
        self._kbd_device = None
        self._mouse_sub = None
        self._mouse_device = None
        self._carb_input = None

    def _record_first_user_action(self, source: str, action: str) -> None:
        gate = self._user_action_gate
        generation = self._load_generation
        if self._state != _St.NAVIGATING or gate is None or not gate.consume(generation):
            return
        self._record_load_event(
            generation, "FIRST_USER_ACTION", signal="carb_input", source=source, action=action
        )

    def _on_mouse(self, event, *_args) -> bool:
        if self._state != _St.NAVIGATING:
            return False
        meaningful = (
            carb.input.MouseEventType.LEFT_BUTTON_DOWN,
            carb.input.MouseEventType.RIGHT_BUTTON_DOWN,
            carb.input.MouseEventType.MIDDLE_BUTTON_DOWN,
            carb.input.MouseEventType.SCROLL,
        )
        if event.type in meaningful:
            self._record_first_user_action("mouse", str(event.type))
        return False

    def _on_key(self, event, *_args) -> bool:
        if event.type != carb.input.KeyboardEventType.KEY_PRESS:
            return False
        key = event.input
        KI  = carb.input.KeyboardInput

        if self._state == _St.NAVIGATING:
            self._record_first_user_action("keyboard", str(key))
            if key == KI.R:
                self._reset_camera()
                return True
            if key == KI.ENTER:
                self._open_scoring()
                return True

        elif self._state == _St.SCORING:
            if key == KI.ESCAPE:
                self._close_scoring()
                return True

        return False

    # ── Deferred startup ───────────────────────────────────────────────────────

    async def _deferred_start(self) -> None:
        app = omni.kit.app.get_app()
        for _ in range(8):
            await app.next_update_async()
        omni.log.info(f"[{_EXT_ID}] Showing participant prompt.")
        self._build_prompt_win()

    # ── Participant prompt ─────────────────────────────────────────────────────

    def _build_prompt_win(self) -> None:
        self._prompt_win = ui.Window(
            "Participant",
            width=_PROMPT_WIN_WIDTH,
            height=_PROMPT_WIN_HEIGHT,
            flags=modal_window_flags(ui),
        )
        self._name_model = ui.SimpleStringModel("")
        self._prompt_win.frame.set_style(modal_frame_style())
        with self._prompt_win.frame:
            with ui.VStack(spacing=16):
                ui.Label(
                    "Participant",
                    style={"color": TEXT_PRIMARY, "font_size": 18},
                )
                ui.Label(
                    "Enter your name to begin the evaluation session:",
                    word_wrap=True,
                    style={"color": TEXT_PRIMARY, "font_size": _PROMPT_FONT_SIZE},
                )
                with ui.HStack(spacing=10, height=_PROMPT_FIELD_H + 4):
                    ui.Label(
                        "Name:",
                        width=_PROMPT_LABEL_W,
                        style={"color": TEXT_PRIMARY, "font_size": _PROMPT_FONT_SIZE},
                    )
                    ui.StringField(
                        model=self._name_model,
                        width=ui.Fraction(1),
                        height=_PROMPT_FIELD_H,
                        style={"font_size": _PROMPT_FONT_SIZE, **text_field_style()},
                    )
                with ui.HStack(spacing=10, height=_PROMPT_BTN_H + 8):
                    ui.Spacer()
                    self._continue_btn = ui.Button(
                        "Continue",
                        width=_PROMPT_BTN_W,
                        height=_PROMPT_BTN_H,
                        style={"font_size": _PROMPT_FONT_SIZE, **primary_button_style()},
                        clicked_fn=self._on_continue,
                    )
                    ui.Spacer()

        try:
            self._name_model.add_value_changed_fn(
                lambda _: self._refresh_continue_btn()
            )
        except Exception:
            pass
        self._refresh_continue_btn()

    def _refresh_continue_btn(self) -> None:
        if self._continue_btn is None:
            return
        try:
            name = self._name_model.get_value_as_string().strip()
            self._continue_btn.enabled = len(name) >= 1
        except Exception:
            pass

    def _on_continue(self) -> None:
        try:
            name = self._name_model.get_value_as_string().strip()
        except Exception:
            name = ""
        if not name:
            return
        self._participant = name
        if self._prompt_win:
            self._prompt_win.visible = False
        omni.log.info(f"[{_EXT_ID}] Participant: {self._participant!r}")
        asyncio.ensure_future(self._start_evaluation())

    # ── Evaluation startup ─────────────────────────────────────────────────────

    async def _start_evaluation(self) -> None:
        # Resolve scene list path
        scene_list_path = self._resolve_scene_list_path()
        if not scene_list_path or not os.path.isfile(scene_list_path):
            self._show_error(
                f"Scene list file not found.\n\nExpected at:\n{scene_list_path}"
            )
            return

        try:
            self._scenes = _load_scene_list(scene_list_path)
        except Exception as exc:
            self._show_error(f"Failed to load scene list:\n{exc}")
            return

        total_in_list = len(self._scenes)
        self._scenes, skipped = _filter_unscored_scenes(
            self._scenes, self._participant
        )
        if skipped:
            omni.log.info(
                f"[{_EXT_ID}] Skipping {skipped}/{total_in_list} already-scored "
                f"scene(s) for {self._participant!r}"
            )

        if not self._scenes:
            self._build_status_win()
            if skipped > 0:
                self._state = _St.DONE
                self._set_status(
                    f"All {skipped} scene(s) already scored for "
                    f"'{self._participant}'."
                )
                self._show_completion(already_complete=True, total=skipped)
            else:
                self._show_error(
                    "Scene list contains no valid .usdz files.\n"
                    f"(Loaded from: {scene_list_path})"
                )
            return

        omni.log.info(
            f"[{_EXT_ID}] Loaded {len(self._scenes)} scene(s) to evaluate "
            f"({skipped} skipped) from {scene_list_path}"
        )

        # Build persistent UI
        self._build_status_win()
        self._build_scoring_win()

        # Start with first scene
        self._index = 0
        await omni.kit.app.get_app().next_update_async()
        self._load_scene()

    def _resolve_scene_list_path(self) -> str:
        tokens = carb.tokens.get_tokens_interface()
        s = carb.settings.get_settings()

        # 1. Setting (set in nycu.mos_app.kit, supports ${app} tokens).
        try:
            raw = s.get_as_string(f"/exts/{_EXT_ID}/sceneListPath")
            if raw:
                path = tokens.resolve(raw)
                if path and os.path.isfile(path):
                    return path
        except Exception:
            pass

        # 2. Default next to the app's data folder.
        for raw in [
            "${app}/../data/mos_scenes.json",
            "${kit_sdk_path}/../data/mos_scenes.json",
        ]:
            try:
                path = tokens.resolve(raw)
                if path and os.path.isfile(path):
                    return path
            except Exception:
                pass

        # 3. Hard-coded fallback: source tree data folder.
        src_fallback = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..",
            "source", "data", "mos_scenes.json",
        )
        src_fallback = os.path.normpath(src_fallback)
        if os.path.isfile(src_fallback):
            return src_fallback

        # 4. CWD fallback.
        return os.path.join(os.getcwd(), "data", "mos_scenes.json")

    # ── Status overlay ─────────────────────────────────────────────────────────

    def _app_window_size(self) -> Tuple[int, int]:
        try:
            import omni.appwindow
            app_window = omni.appwindow.get_default_app_window()
            if app_window is not None:
                return int(app_window.get_width()), int(app_window.get_height())
        except Exception:
            pass
        try:
            s = carb.settings.get_settings()
            w = int(s.get_as_float("/app/renderer/resolution/width") or 1920)
            h = int(s.get_as_float("/app/renderer/resolution/height") or 1080)
            return w, h
        except Exception:
            return 1920, 1080

    def _status_text_width(self, msg: str) -> int:
        # Proportional-font width estimate (px) for right-sized HUD bar.
        omni.log.warn(f"[{_EXT_ID}] Status text width: {len(msg) * _STATUS_FONT_SIZE * 0.52} + {_STATUS_HPAD}")
        return int(len(msg) * _STATUS_FONT_SIZE * 0.52) + _STATUS_HPAD

    def _resize_status_win(self, msg: str) -> None:
        if self._status_win is None:
            return
        try:
            self._status_win.width = min(
                max(self._status_text_width(msg), _STATUS_MIN_WIDTH),
                _STATUS_MAX_WIDTH,
            )
            omni.log.warn(f"[{_EXT_ID}] Status window width: {self._status_win.width}")
        except Exception:
            pass

    def _position_status_win(self) -> None:
        if self._status_win is None:
            return
        try:
            app_w, _ = self._app_window_size()
            win_w = int(self._status_win.width or _STATUS_MIN_WIDTH)
            self._status_win.position_x = max(
                _STATUS_MARGIN,
                app_w - win_w - _STATUS_MARGIN,
            )
            omni.log.warn(f"[{_EXT_ID}] Status window position: {self._status_win.position_x}, {self._status_win.position_y}")
            self._status_win.position_y = _STATUS_MARGIN
        except Exception:
            pass

    def _build_status_win(self) -> None:
        app_w, _ = self._app_window_size()
        self._status_win = ui.Window(
            "MOS Status",
            width=_STATUS_MIN_WIDTH,
            height=_STATUS_HEIGHT,
            position_x=max(_STATUS_MARGIN, app_w - _STATUS_MIN_WIDTH - _STATUS_MARGIN),
            position_y=_STATUS_MARGIN,
            dockPreference=ui.DockPreference.DISABLED,
            flags=(
                ui.WINDOW_FLAGS_NO_TITLE_BAR
                | ui.WINDOW_FLAGS_NO_SCROLLBAR
                | ui.WINDOW_FLAGS_NO_RESIZE
                | ui.WINDOW_FLAGS_NO_DOCKING
            ),
        )
        self._status_win.padding_x = 12
        self._status_win.padding_y = 0
        omni.log.warn(f"[{_EXT_ID}] Status window padding: {self._status_win.padding_x}, {self._status_win.padding_y}")
        with self._status_win.frame:
            with ui.VStack(height=ui.Fraction(1)):
                ui.Spacer()
                with ui.HStack(spacing=0, height=0):
                    #ui.Spacer(width=ui.Fraction(1))
                    self._status_lbl = ui.Label(
                        "Loading …",
                        word_wrap=False,
                        alignment=ui.Alignment.RIGHT_CENTER,
                        style={"color": 0xFFDDDDDD, "font_size": _STATUS_FONT_SIZE},
                    )
                ui.Spacer()

        asyncio.ensure_future(self._deferred_position_status())

    async def _deferred_position_status(self) -> None:
        app = omni.kit.app.get_app()
        for _ in range(4):
            await app.next_update_async()
        self._position_status_win()

    def _set_status(self, msg: str) -> None:
        try:
            omni.log.warn(f"[{_EXT_ID}] Setting status: {msg}")
            if self._status_lbl is not None:
                self._status_lbl.text = msg
            self._resize_status_win(msg)
            self._position_status_win()
        except Exception:
            pass

    def _show_error(self, msg: str) -> None:
        omni.log.error(f"[{_EXT_ID}] {msg}")
        self._set_status(f"ERROR: {msg}")
        try:
            err = ui.Window(
                "MOS Error",
                width=480, height=160,
                flags=ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_DOCKING,
            )
            with err.frame:
                with ui.VStack(spacing=10):
                    ui.Label(msg, word_wrap=True)
                    with ui.HStack(height=36):
                        ui.Spacer()
                        ui.Button(
                            "OK",
                            width=80,
                            clicked_fn=lambda: setattr(err, "visible", False),
                        )
                        ui.Spacer()
            self._err_win = err
        except Exception:
            pass

    # ── Scene loading ──────────────────────────────────────────────────────────

    def _record_load_event(self, generation: int, event: str, **fields: Any) -> None:
        if generation != self._load_generation or self._load_diag is None:
            return
        self._load_diag.record(event, **fields)

    def _clear_load_subscriptions(self) -> None:
        self._stage_sub = None
        self._render_sub = None
        self._renderer_subs = []
        if self._capture_task is not None:
            self._capture_task.cancel()
        self._capture_task = None
        self._stability_start_gate.clear()
        self._capture_baseline = None
        self._capture_previous = None
        self._capture_sample_count = 0

    def _schedule_renderer_checks(self, generation: int) -> None:
        """Record the first valid renderer lifecycle event for this scene."""
        try:
            import omni.appwindow
            import carb.eventdispatcher
            from omni.kit.renderer import bind as renderer_bind

            app_window = omni.appwindow.get_default_app_window()
            dispatcher = carb.eventdispatcher.get_eventdispatcher()
            phases = (
                ("FIRST_RENDER_COMMAND", renderer_bind.RendererEventType.PRE_BEGIN_FRAME),
                ("FIRST_DISPLAYABLE_RENDER_FRAME", renderer_bind.RendererEventType.RENDER_FRAME),
                ("FIRST_PRESENT_TO_VIEWPORT", renderer_bind.RendererEventType.PRESENT_RENDER_FRAME),
                ("POST_PRESENT_FRAME_BUFFER", renderer_bind.RendererEventType.POST_PRESENT_FRAME_BUFFER),
            )
            self._renderer_subs = [
                dispatcher.observe_event(
                    observer_name=f"mos_app_{phase.lower()}",
                    event_name=renderer_bind.get_renderer_event_name(event_type, app_window),
                    order=0,
                    on_event=lambda event, phase=phase: self._on_renderer_event(event, generation, phase),
                )
                for phase, event_type in phases
            ]
        except Exception as exc:
            self._renderer_subs = []
            self._record_load_event(
                generation, "RENDERER_EVENTS_UNAVAILABLE", error=type(exc).__name__)

    @staticmethod
    def _renderer_event_value(event: Any, key: str, default: Any) -> Any:
        try:
            return event.get(key) if key in event else default
        except Exception:
            return default

    def _on_renderer_event(self, event: Any, generation: int, phase: str) -> None:
        gate = self._renderer_phase_gate
        if generation != self._load_generation or gate is None:
            return
        save_draw_data = bool(self._renderer_event_value(event, "saveDrawData", False))
        draw_frozen = bool(self._renderer_event_value(event, "draw_frozen", False))
        if save_draw_data or draw_frozen:
            return
        if not gate.consume(generation, phase):
            return
        self._record_load_event(
            generation, phase, signal="renderer_event", save_draw_data=save_draw_data,
            draw_frozen=draw_frozen)
        if phase == "POST_PRESENT_FRAME_BUFFER":
            self._begin_stability_sampling(generation)
        if gate.complete:
            self._renderer_subs = []

    @staticmethod
    def _frame_signature(values: List[int]) -> Tuple[int, ...]:
        if not values:
            return ()
        step = max(1, len(values) // _STABILITY_SIGNATURE_SAMPLES)
        return tuple(values[::step][:_STABILITY_SIGNATURE_SAMPLES])

    @staticmethod
    def _mean_frame_delta(left: Tuple[int, ...], right: Tuple[int, ...]) -> int:
        if not left or not right or len(left) != len(right):
            return 255
        return round(sum(abs(a - b) for a, b in zip(left, right)) / len(left))

    def _request_viewport_capture(self, generation: int, kind: str) -> None:
        try:
            import omni.appwindow
            import omni.kit.renderer_capture

            app_window = omni.appwindow.get_default_app_window()
            capture = omni.kit.renderer_capture.acquire_renderer_capture_interface()
            if app_window is None or capture is None:
                raise RuntimeError("capture window/interface unavailable")
            capture.capture_next_frame_swapchain_callback(
                lambda buf, size, width, height, fmt: self._on_viewport_capture(
                    buf, size, width, height, fmt, generation, kind
                ),
                app_window,
            )
            self._record_load_event(generation, "VIEWPORT_CAPTURE_REQUESTED", kind=kind)
        except Exception as exc:
            self._record_load_event(
                generation, "VIEWPORT_CAPTURE_UNAVAILABLE", error=type(exc).__name__
            )

    def _schedule_baseline_capture(self, generation: int) -> None:
        self._request_viewport_capture(generation, "baseline")

    def _begin_stability_sampling(self, generation: int) -> None:
        if generation != self._load_generation or self._capture_task is not None:
            return
        # Renderer events arrive on a renderer-owned thread. Queue the work for
        # the permanent Kit update subscription, where asyncio is available.
        self._stability_start_gate.schedule(generation)
        self._record_load_event(generation, "STABILITY_SAMPLING_QUEUED", signal="kit_update")

    def _on_stability_start_update(self, _event: Any) -> None:
        generation = self._load_generation
        if not self._stability_start_gate.consume(generation) or self._capture_task is not None:
            return
        self._frame_stability_gate = _FrameStabilityGate(
            generation, _STABILITY_REQUIRED_CONSECUTIVE, _STABILITY_MAX_MEAN_DELTA
        )
        self._capture_task = asyncio.ensure_future(
            self._capture_viewport_samples(generation)
        )

    async def _capture_viewport_samples(self, generation: int) -> None:
        app = omni.kit.app.get_app()
        try:
            for _ in range(_STABILITY_CAPTURE_COUNT):
                if generation != self._load_generation:
                    return
                for _ in range(_STABILITY_CAPTURE_GAP_UPDATES):
                    await app.next_update_async()
                self._request_viewport_capture(generation, "sample")
        except asyncio.CancelledError:
            return
        finally:
            if generation == self._load_generation:
                self._capture_task = None

    def _on_viewport_capture(
        self, buffer: Any, buffer_size: int, width: int, height: int, fmt: Any,
        generation: int, kind: str
    ) -> None:
        if generation != self._load_generation:
            return
        try:
            import omni.kit.renderer_capture
            values = omni.kit.renderer_capture.convert_raw_bytes_to_list(
                buffer, buffer_size, width, height, fmt
            )
            signature = self._frame_signature(values)
        except Exception as exc:
            self._record_load_event(
                generation, "VIEWPORT_CAPTURE_FAILED", error=type(exc).__name__
            )
            return
        if kind == "baseline":
            self._capture_baseline = signature
            self._record_load_event(
                generation, "VIEWPORT_BASELINE_CAPTURED", width=width, height=height
            )
            return
        self._capture_sample_count += 1
        previous = self._capture_previous
        self._capture_previous = signature
        if previous is None:
            self._record_load_event(
                generation, "CAPTURED_VIEWPORT_FRAME", signal="swapchain_capture",
                width=width, height=height
            )
            self._record_load_event(
                generation, "VIEWPORT_SAMPLE", sample=self._capture_sample_count,
                width=width, height=height, mean_delta="n/a"
            )
            return
        delta = self._mean_frame_delta(previous, signature)
        self._record_load_event(
            generation, "VIEWPORT_SAMPLE", sample=self._capture_sample_count,
            width=width, height=height, mean_delta=delta
        )
        gate = self._frame_stability_gate
        if gate is not None and gate.consume(generation, delta):
            baseline_delta = self._mean_frame_delta(self._capture_baseline or (), signature)
            self._record_load_event(
                generation, "RENDER_STABLE", signal="swapchain_capture",
                mean_delta=delta, baseline_delta=baseline_delta
            )

    def _schedule_post_load_update(self, generation: int) -> None:
        try:
            self._render_sub = (
                omni.kit.app.get_app()
                .get_update_event_stream()
                .create_subscription_to_pop(
                    lambda event: self._on_first_post_load_update(event, generation),
                    name="mos_app_post_load_update",
                )
            )
        except Exception as exc:
            self._record_load_event(
                generation, "FIRST_POST_LOAD_UPDATE_UNAVAILABLE", error=type(exc).__name__)

    def _on_first_post_load_update(self, _event: Any, generation: int) -> None:
        gate = self._readiness_gate
        if generation != self._load_generation or gate is None or not gate.consume(generation):
            return
        self._record_load_event(generation, "FIRST_POST_LOAD_UPDATE", signal="kit_update")
        self._render_sub = None

    def _load_scene(self) -> None:
        path = self._scenes[self._index]
        n    = len(self._scenes)
        self._clear_load_subscriptions()
        self._load_generation += 1
        generation = self._load_generation
        self._load_diag = _LoadDiagnostics(
            self._index + 1, n, path, generation=generation)
        self._load_diag.begin()
        self._readiness_gate = _ReadinessGate(generation)
        self._user_action_gate = _ReadinessGate(generation)
        self._frame_stability_gate = None
        self._renderer_phase_gate = _RendererPhaseGate(
            generation,
            (
                "FIRST_RENDER_COMMAND",
                "FIRST_DISPLAYABLE_RENDER_FRAME",
                "FIRST_PRESENT_TO_VIEWPORT",
                "POST_PRESENT_FRAME_BUFFER",
            ),
        )
        self._record_load_event(generation, "BEGIN")
        omni.log.warn(
            f"[{_EXT_ID}] Loading {self._index + 1}/{n}: {path}"
        )
        self._set_status(
            f"Loading scene {self._index + 1}/{n}: {os.path.basename(path)} …"
        )
        self._state = _St.LOADING
        self._initial_cam_xform = None

        abs_url = os.path.normcase(os.path.abspath(path))
        self._pending_abs_path = abs_url

        # Subscribe BEFORE opening so we never miss the OPENED event.
        try:
            self._stage_sub = (
                omni.usd.get_context()
                .get_stage_event_stream()
                .create_subscription_to_pop(
                    lambda event: self._on_stage_event(event, generation), name="mos_app_load"
                )
            )
        except Exception as exc:
            self._record_load_event(
                generation, "STAGE_SUBSCRIBE_FAILED", error=type(exc).__name__)
            omni.log.error(f"[{_EXT_ID}] Stage subscribe failed: {exc}")
            self._pending_abs_path = None
            return

        self._schedule_baseline_capture(generation)

        try:
            _unload_stage()
            omni.usd.get_context().open_stage(path)
        except Exception as exc:
            self._record_load_event(
                generation, "STAGE_OPEN_FAILED", error=type(exc).__name__)
            self._stage_sub = None
            self._pending_abs_path = None
            self._show_error(f"open_stage failed:\n{exc}")

    def _on_stage_event(self, event, generation: int) -> None:
        if generation != self._load_generation:
            return
        pending = self._pending_abs_path
        if pending is None:
            return

        et     = event.type
        opened = int(omni.usd.StageEventType.OPENED)
        failed = int(getattr(omni.usd.StageEventType, "OPEN_FAILED", -1))

        if et == failed:
            self._record_load_event(generation, "STAGE_OPEN_FAILED", error="stage_event")
            self._stage_sub = None
            self._pending_abs_path = None
            self._show_error("Stage open failed.")
            self._state = _St.NAVIGATING
            return

        if et != opened:
            return

        # Verify this is our target stage, not the empty stage from unload.
        try:
            url = omni.usd.get_context().get_stage_url() or ""
            url = os.path.normcase(os.path.abspath(url))
            if url != pending:
                return
        except Exception:
            pass

        self._stage_sub        = None
        self._pending_abs_path = None
        self._record_load_event(generation, "STAGE_OPENED")
        # Subscribe before camera/UI post-processing so the first render phases
        # after opening cannot be missed.
        self._schedule_renderer_checks(generation)
        self._post_load(generation)

    def _post_load(self, generation: int) -> None:
        path = self._scenes[self._index]

        # 1. Orientation fix
        orientation_ok = True
        try:
            _apply_orientation(
                _ORIENT_PRESET, _FORCE_Z_UP, _CAMERA_CONVENTION.stage_up_axis
            )
        except Exception as exc:
            orientation_ok = False
            omni.log.warn(f"[{_EXT_ID}] Orientation failed: {exc}")
        self._record_load_event(generation, "ORIENTATION_DONE", ok=orientation_ok)

        # 2. Camera from cameras.json
        cam_json = _resolve_cameras_json(path)
        cam_tag  = "no cameras.json"
        camera_ready = False
        if cam_json:
            cam0 = _load_camera0(cam_json)
            if cam0 and _apply_camera_from_json(cam0, _ORIENT_PRESET):
                cam_tag = f"camera OK ({os.path.basename(cam_json)})"
                camera_ready = True
            else:
                cam_tag = "camera FAILED"

        if camera_ready:
            self._record_load_event(
                generation, "CAMERA_READY", source=os.path.basename(cam_json))
        else:
            reason = "missing_cameras_json" if not cam_json else "camera_setup_failed"
            self._record_load_event(generation, "CAMERA_FALLBACK", reason=reason)

        # 3. Capture initial camera pose for reset
        self._capture_initial_camera()

        # 4. Update UI
        n    = len(self._scenes)
        idx  = self._index
        fname = os.path.basename(path)
        self._set_status(
            f"Scene {idx + 1}/{n}: {fname}  |  {cam_tag}"
            f"  |  [R] reset    [Enter] scoring    [Esc] close panel"
        )
        self._update_scene_info()

        self._state = _St.NAVIGATING
        self._record_load_event(generation, "NAV_READY")
        self._schedule_post_load_update(generation)
        omni.log.info(f"[{_EXT_ID}] Post-load done — {fname}")

    # ── Camera capture & reset ─────────────────────────────────────────────────

    def _capture_initial_camera(self) -> None:
        try:
            from pxr import UsdGeom
            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return
            prim = stage.GetPrimAtPath("/BrowserCamera")
            if not prim or not prim.IsValid():
                omni.log.info(
                    f"[{_EXT_ID}] /BrowserCamera not found; reset unavailable."
                )
                return
            xf  = UsdGeom.Xformable(prim)
            ops = xf.GetOrderedXformOps()
            if ops:
                self._initial_cam_xform = ops[0].Get()
                omni.log.info(f"[{_EXT_ID}] Initial camera captured.")
        except Exception as exc:
            omni.log.warn(f"[{_EXT_ID}] Capture camera failed: {exc}")

    def _reset_camera(self) -> None:
        if self._initial_cam_xform is None:
            omni.log.info(f"[{_EXT_ID}] No initial camera stored (no cameras.json?).")
            return
        try:
            from pxr import UsdGeom
            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return
            prim = stage.GetPrimAtPath("/BrowserCamera")
            if not prim or not prim.IsValid():
                return
            xf  = UsdGeom.Xformable(prim)
            ops = xf.GetOrderedXformOps()
            if ops:
                ops[0].Set(self._initial_cam_xform)
            else:
                xf.AddTransformOp().Set(self._initial_cam_xform)
            # Re-activate
            try:
                import omni.kit.viewport.utility as vpu
                vp = getattr(vpu, "get_active_viewport", lambda: None)()
                if vp and hasattr(vp, "set_active_camera"):
                    vp.set_active_camera("/BrowserCamera")
            except Exception:
                pass
            omni.log.info(f"[{_EXT_ID}] Camera reset to initial pose.")
        except Exception as exc:
            omni.log.warn(f"[{_EXT_ID}] Reset camera failed: {exc}")

    # ── Scoring window ─────────────────────────────────────────────────────────

    def _build_scoring_win(self) -> None:
        self._scoring_win = ui.Window(
            "Scene Scoring",
            width=_SCORE_WIN_WIDTH,
            height=_SCORE_WIN_HEIGHT,
            visible=False,
            flags=modal_window_flags(ui),
        )
        self._scoring_win.frame.set_style(modal_frame_style())
        self._score_models      = {}
        self._score_step_labels = {}
        self._score_value_labels = {}

        with self._scoring_win.frame:
            with ui.VStack(spacing=10):
                # Header
                ui.Label(
                    "Scene Scoring",
                    style={"color": TEXT_PRIMARY, "font_size": 18},
                )
                ui.Label(
                    f"Participant: {self._participant}",
                    style={"color": PARTICIPANT_ACCENT, "font_size": _SCORE_HEADER_SIZE},
                )
                ui.Separator()

                # One row per metric
                for key, label in _METRICS:
                    model = ui.SimpleIntModel(3)
                    self._score_models[key] = model

                    with ui.HStack(spacing=12, height=_SCORE_ROW_H):
                        ui.Label(
                            label,
                            width=_SCORE_LABEL_W,
                            height=_SCORE_ROW_H,
                            word_wrap=False,
                            alignment=ui.Alignment.LEFT_CENTER,
                            style={"color": TEXT_PRIMARY, "font_size": _SCORE_FONT_SIZE},
                        )
                        with ui.VStack(width=_SCORE_SLIDER_W, height=_SCORE_ROW_H):
                            ui.Spacer()
                            ui.IntSlider(
                                model=model,
                                min=1,
                                max=5,
                                width=_SCORE_SLIDER_W,
                                height=_SCORE_SLIDER_H,
                                style=_SLIDER_STYLE,
                            )
                            ui.Spacer()
                        value_lbl = ui.Label(
                            "3",
                            width=_SCORE_VALUE_W,
                            height=_SCORE_ROW_H,
                            alignment=ui.Alignment.CENTER,
                            style={"color": TEXT_PRIMARY, "font_size": _SCORE_FONT_SIZE},
                        )
                        step_lbl = ui.Label(
                            _SLIDER_STEPS[2],  # "Average" = index 2 = value 3
                            width=_SCORE_STEP_W,
                            height=_SCORE_ROW_H,
                            alignment=ui.Alignment.LEFT_CENTER,
                            style={"color": TEXT_PRIMARY, "font_size": _SCORE_FONT_SIZE},
                        )
                        self._score_step_labels[key] = step_lbl
                        self._score_value_labels[key] = value_lbl

                        def _make_cb(
                            step: ui.Label,
                            value: ui.Label,
                            m: ui.SimpleIntModel,
                        ):
                            def _cb(_model: ui.AbstractValueModel) -> None:
                                try:
                                    v = max(1, min(5, int(m.get_value_as_int())))
                                    step.text = _SLIDER_STEPS[v - 1]
                                    value.text = str(v)
                                except Exception:
                                    pass
                            return _cb

                        try:
                            model.add_value_changed_fn(
                                _make_cb(step_lbl, value_lbl, model)
                            )
                        except Exception:
                            pass

                ui.Separator()

                with ui.HStack(spacing=12, height=_SCORE_BTN_H + 8):
                    ui.Spacer()
                    ui.Button(
                        "Next  ▶",
                        width=_SCORE_BTN_W,
                        height=_SCORE_BTN_H,
                        style={"font_size": _SCORE_FONT_SIZE, **primary_button_style()},
                        clicked_fn=self._on_next,
                    )
                    ui.Spacer()

                self._scene_info_lbl = ui.Label(
                    "",
                    word_wrap=True,
                    style={"color": TEXT_MUTED, "font_size": _SCORE_FONT_SIZE},
                )
                self._scoring_hint_lbl = ui.Label(
                    "Press Esc to close without submitting.",
                    style={"color": TEXT_HINT, "font_size": _SCORE_FOOTER_SIZE},
                )

        self._update_scene_info()

    def _update_scene_info(self) -> None:
        if self._scene_info_lbl is None or not self._scenes:
            return
        idx   = self._index
        n     = len(self._scenes)
        fname = os.path.basename(self._scenes[idx])
        try:
            self._scene_info_lbl.text = f"Scene {idx + 1} / {n}  ·  {fname}"
        except Exception:
            pass

    def _open_scoring(self) -> None:
        if self._scoring_win is None:
            return
        self._scoring_win.visible = True
        self._state = _St.SCORING

    def _close_scoring(self) -> None:
        if self._scoring_win is None:
            return
        self._scoring_win.visible = False
        self._state = _St.NAVIGATING

    def _on_next(self) -> None:
        if not self._save_scores():
            return  # error surfaced inside _save_scores
        self._close_scoring()

        n = len(self._scenes)
        if self._index >= n - 1:
            self._state = _St.DONE
            self._set_status(
                f"All {n} scenes evaluated. Scores saved for '{self._participant}'."
            )
            self._show_completion()
        else:
            self._index += 1
            self._reset_sliders()
            self._load_scene()

    def _reset_sliders(self) -> None:
        for model in self._score_models.values():
            try:
                model.set_value(3)
            except Exception:
                pass

    def _show_completion(
        self, *, already_complete: bool = False, total: int = 0
    ) -> None:
        n = total if already_complete else len(self._scenes)
        win = ui.Window(
            "Evaluation Complete",
            width=440, height=130,
            flags=ui.WINDOW_FLAGS_NO_SCROLLBAR | ui.WINDOW_FLAGS_NO_DOCKING,
        )
        with win.frame:
            with ui.VStack(spacing=10):
                if already_complete:
                    msg = (
                        f"All {n} scene(s) were already scored.\n"
                        f"Participant: {self._participant}"
                    )
                else:
                    msg = (
                        f"All {n} scene(s) evaluated.\n"
                        f"Scores saved for participant: {self._participant}"
                    )
                ui.Label(
                    msg,
                    word_wrap=True,
                    style={"font_size": 14},
                )
                with ui.HStack(height=36):
                    ui.Spacer()
                    ui.Button(
                        "Close",
                        width=90,
                        clicked_fn=lambda: setattr(win, "visible", False),
                    )
                    ui.Spacer()
        self._completion_win = win

    # ── Score persistence ──────────────────────────────────────────────────────

    def _collect_scores(self) -> Dict[str, int]:
        return {
            key: max(1, min(5, int(self._score_models[key].get_value_as_int())))
            for key, _ in _METRICS
            if key in self._score_models
        }

    def _save_scores(self) -> bool:
        try:
            path = _score_file(self._participant)
            data = _read_json(path)
            if not isinstance(data, dict):
                data = {
                    "version": 1,
                    "participant": self._participant,
                    "sessions": [],
                }
            sessions: list = data.setdefault("sessions", [])
            sessions.append({
                "saved_at":    _now_iso(),
                "scene_path":  _normalize_scene_path(self._scenes[self._index]),
                "scene_index": self._index,
                "scores":      self._collect_scores(),
            })
            _write_json(path, data)
            omni.log.info(f"[{_EXT_ID}] Scores saved → {path}")
            return True
        except Exception as exc:
            self._show_error(f"Failed to save scores:\n{exc}")
            return False
