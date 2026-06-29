# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

from __future__ import annotations

import gc
import json
import os
import random
from math import sqrt
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import carb.settings
import omni.ext
import omni.ui as ui
import omni.log
import omni.usd


# ── Persistent settings keys ──────────────────────────────────────────────────
_S = "/persistent/exts/usdz_folder_browser/"
_KEY_FOLDER    = _S + "lastFolder"
_KEY_RECURSIVE = _S + "recursive"
_KEY_ROT_W2C   = _S + "rotW2C"
_KEY_CV_AXES   = _S + "opencvAxes"
_KEY_SWAP_YZ   = _S + "swapYZ"
_KEY_OVERRIDE  = _S + "camOverride"
_KEY_PAT0      = _S + "camPattern0"
_KEY_PAT1      = _S + "camPattern1"
_KEY_PAT2      = _S + "camPattern2"

_DEFAULT_PAT0 = "geom_optim/output/cameras.json"
_DEFAULT_PAT1 = "cameras.json"

# Applied automatically on every load (no UI).
_SCENE_ORIENT_PRESET = "rx-90"
_FORCE_Z_UP = True

# Optional file picker — imported at runtime so the extension resolver never
# hard-fails on its absence in minimal (non-full-editor) configurations.
try:
    from omni.kit.window.filepicker import FilePickerDialog as _FilePickerDialog
    _HAS_FILEPICKER = True
except Exception:
    _FilePickerDialog = None  # type: ignore[assignment,misc]
    _HAS_FILEPICKER = False


# ── File scanning ─────────────────────────────────────────────────────────────

def _scan_usdz(folder: str, recursive: bool) -> List[str]:
    folder = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(folder):
        omni.log.warn(f"Not a directory: {folder}")
        return []
    out: List[str] = []     # Stores paths towards .usdz files
    if recursive:
        for root, dirs, files in os.walk(folder):
            dirs.sort()  # sort in-place so os.walk visits subdirs alphabetically
            for f in sorted(files):
                if f.lower().endswith(".usdz"):
                    out.append(os.path.join(root, f))
        omni.log.warn(f"Found {len(out)} .usdz files in {folder}")
    else:
        for f in sorted(os.listdir(folder)):
            full = os.path.join(folder, f)
            if os.path.isfile(full) and f.lower().endswith(".usdz"):
                out.append(full)
        omni.log.warn(f"Found {len(out)} .usdz files in {folder} (non-recursive)")
    return out


# ── cameras.json resolution ───────────────────────────────────────────────────

def _resolve_cameras_json(
    scene_path: str,
    patterns: List[str],
    override: str = "",
) -> Optional[str]:
    """Return the cameras.json path to use for *scene_path*.

    Priority:
    1. *override* — used verbatim if non-empty and the file exists.
    2. Walk-up search — at each ancestor directory of *scene_path*, try every
       pattern in *patterns* as a relative path.
    """
    if patterns:
        omni.log.warn(f"Trying patterns: {patterns}")
    if override:
        candidate = os.path.abspath(os.path.expanduser(override))
        if os.path.isfile(candidate):
            omni.log.warn(f"Using override path for cameras.json: {candidate}")
            return candidate

    active = [p.strip() for p in patterns if p.strip()]
    if not active:
        return None

    cur = os.path.abspath(os.path.dirname(scene_path))
    prev = None
    while cur and cur != prev:
        for pattern in active:
            parts = pattern.replace("\\", "/").split("/")
            candidate = os.path.normpath(os.path.join(cur, *parts)) # * unpacks parts list into positional arguments
            if os.path.isfile(candidate):
                omni.log.info(f"Using pattern {pattern} and found cameras.json: {candidate}")
                return candidate
        prev = cur
        cur = os.path.dirname(cur)
    omni.log.info(f"No cameras.json found using patterns: {active}")
    return None


def _load_camera0(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            omni.log.info(f"Loaded cameras.json from: {path}")
        if isinstance(data, list) and data:
            cam0 = data[0]
            omni.log.info(f"Loaded camera 0 from: {path}\n camera0: {cam0}")
            return cam0 if isinstance(cam0, dict) else None
    except Exception:
        omni.log.info(f"Error loading cameras.json from: {path}")
        pass
    return None


# ── Matrix helpers ────────────────────────────────────────────────────────────

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
    return ((m[0][0], m[1][0], m[2][0]),
            (m[0][1], m[1][1], m[2][1]),
            (m[0][2], m[1][2], m[2][2]))


def _mm(a, b):
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )


def _mv(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


# ── USD / viewport operations ─────────────────────────────────────────────────

def _scene_preset_rot3(preset: str):
    """Return a 3×3 rotation matrix for a scene-orientation preset name."""
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


def _apply_camera(
    cam: Dict[str, Any],
    rot_is_w2c: bool = False,
    cv_axes: bool = False,
    swap_yz: bool = False,
    scene_preset: str = "none",
) -> bool:
    pos = _vec3(cam.get("position"))
    rot = _mat3(cam.get("rotation"))
    if pos is None or rot is None:
        return False

    try:
        import omni.usd
        from pxr import Gf, Sdf, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return False

        r, p = rot, pos
        if rot_is_w2c:
            r = _T(r)
        if cv_axes:
            r = _mm(r, ((1, 0, 0), (0, -1, 0), (0, 0, -1)))
        if swap_yz:
            swp = ((1, 0, 0), (0, 0, 1), (0, 1, 0))
            r = _mm(swp, r)
            p = _mv(swp, p)

        # /BrowserCamera lives outside /World, so bake the same scene-orientation
        # rotation into the camera pose to keep view aligned with rotated content.
        pr = _scene_preset_rot3(scene_preset)
        if pr is not None and scene_preset != "none":
            r = _mm(pr, r)
            p = _mv(pr, p)

        r0, r1, r2 = r
        xform = Gf.Matrix4d(
            r0[0], r0[1], r0[2], 0.0,
            r1[0], r1[1], r1[2], 0.0,
            r2[0], r2[1], r2[2], 0.0,
            p[0],  p[1],  p[2],  1.0,
        )

        # Root-level path avoids inheriting /World xform; scene_preset above
        # applies the matching rotation directly to the camera pose.
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
        w = float(cam.get("width") or 1024)
        h = float(cam.get("height") or 1024)
        fx = cam.get("fx")
        fy = cam.get("fy")
        horiz_ap = 20.955
        vert_ap = horiz_ap * h / w if w > 0 else 15.29
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
    except Exception:
        return False


def _apply_orientation(preset: str, force_z_up: bool) -> bool:
    try:
        import omni.usd
        from pxr import Gf, Sdf, UsdGeom

        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return False

        if force_z_up:
            try:
                UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
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
    except Exception:
        return False


def _unload_stage() -> None:
    try:
        import omni.usd
        omni.usd.get_context().close_stage()
    except Exception:
        pass
    try:
        import omni.usd
        ctx = omni.usd.get_context()
        if hasattr(ctx, "new_stage"):
            ctx.new_stage()
    except Exception:
        pass
    try:
        import omni.kit.commands
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


def _sync_scene_recorder_paths(usdz_path: str) -> None:
    """Update scene_recorder UI paths when a USDZ scene finishes loading."""
    try:
        from scene_recorder.extension import SceneRecorderExtension

        ext = SceneRecorderExtension.get_instance()
        if ext is not None:
            ext.sync_paths_for_usdz(usdz_path)
    except ImportError:
        pass
    except Exception as exc:
        omni.log.warn(f"[usdz_folder_browser] scene_recorder path sync failed: {exc}")


def _open_stage(path: str) -> None:
    import omni.usd
    omni.usd.get_context().open_stage(os.path.abspath(path))


# ── Settings helpers ──────────────────────────────────────────────────────────

def _sget(s, key: str, default: str = "") -> str:
    try:
        v = s.get_as_string(key)
        return v if v is not None else default
    except Exception:
        return default


def _bget(s, key: str, default: bool = False) -> bool:
    try:
        v = s.get(key)
        return bool(v) if v is not None else default
    except Exception:
        return default


# ── State ─────────────────────────────────────────────────────────────────────

@dataclass
class _State:
    files: List[str] = None  # type: ignore[assignment]
    index: int = 0
    shuffled: bool = False

    def __post_init__(self):
        if self.files is None:
            self.files = []


# ── Extension ─────────────────────────────────────────────────────────────────

class UsdzFolderBrowserExtension(omni.ext.IExt):

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_startup(self, _ext_id: str) -> None:
        self._s = carb.settings.get_settings()
        self._state = _State()
        self._subs: list = []
        self._picker = None
        self._stage_sub = None   # stage-event subscription kept alive during async load
        self._pending_load = None  # parameters waiting for stage-OPENED event

        # Restore persisted state
        folder   = _sget(self._s, _KEY_FOLDER, "")
        pat0     = _sget(self._s, _KEY_PAT0, _DEFAULT_PAT0)
        pat1     = _sget(self._s, _KEY_PAT1, _DEFAULT_PAT1)
        pat2     = _sget(self._s, _KEY_PAT2, "")
        override = _sget(self._s, _KEY_OVERRIDE, "")

        # UI models
        self._m_folder    = ui.SimpleStringModel(folder)
        self._m_recursive = ui.SimpleBoolModel(_bget(self._s, _KEY_RECURSIVE, False))
        self._m_index     = ui.SimpleIntModel(0)
        self._m_override  = ui.SimpleStringModel(override)
        self._m_pat       = [
            ui.SimpleStringModel(pat0),
            ui.SimpleStringModel(pat1),
            ui.SimpleStringModel(pat2),
        ]
        self._m_rot_w2c   = ui.SimpleBoolModel(_bget(self._s, _KEY_ROT_W2C, False))
        self._m_cv_axes   = ui.SimpleBoolModel(_bget(self._s, _KEY_CV_AXES, False))
        self._m_swap_yz   = ui.SimpleBoolModel(_bget(self._s, _KEY_SWAP_YZ, False))

        # Runtime-updated labels and buttons
        self._lbl_count:    Optional[ui.Label] = None
        self._lbl_file:     Optional[ui.Label] = None
        self._lbl_cam_json: Optional[ui.Label] = None
        self._lbl_status:   Optional[ui.Label] = None
        self._lbl_shuffle:  Optional[ui.Label] = None
        self._btn_prev:     Optional[ui.Button] = None
        self._btn_next:     Optional[ui.Button] = None
        self._btn_load:     Optional[ui.Button] = None
        self._btn_random:   Optional[ui.Button] = None

        self._build_ui()

        try:
            self._subs.append(
                self._m_index.add_value_changed_fn(lambda _: self._sync_index_from_field())
            )
        except Exception:
            pass

    def on_shutdown(self) -> None:
        self._subs = []
        self._stage_sub = None   # releasing the subscription object cancels it
        self._pending_load = None
        if self._picker is not None:
            try:
                self._picker.destroy()
            except Exception:
                pass
            self._picker = None
        self._window = None

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._window = ui.Window("E3DQA Scene Browser", width=600, height=420)
        with self._window.frame:
            with ui.VStack(spacing=4):
                self._section_folder()
                self._section_playlist()
                ui.Separator()
                with ui.CollapsableFrame("Camera Initialisation", collapsed=False):
                    self._section_camera()
                ui.Separator()
                self._section_status()

    def _section_folder(self) -> None:
        ui.Label("FOLDER", style={"font_size": 13})
        # Path field on its own row so it gets full available width.
        with ui.HStack(spacing=4, height=0):
            ui.Label("Path", width=38)
            ui.StringField(model=self._m_folder, width=ui.Fraction(1))
        # Action buttons + recursive toggle on a separate row beneath.
        with ui.HStack(spacing=6, height=0):
            if _HAS_FILEPICKER:
                ui.Button("Browse", width=75, clicked_fn=self._on_browse)
            ui.Button("Scan", width=65, clicked_fn=self._on_scan)
            ui.Spacer(width=10)
            ui.CheckBox(model=self._m_recursive, width=20)
            ui.Label("Recursive", width=80)
            self._lbl_count = ui.Label("0 files", width=70)
            ui.Spacer()

    def _section_playlist(self) -> None:
        ui.Label("PLAYLIST", style={"font_size": 13})
        with ui.HStack(spacing=4, height=0):
            self._btn_prev   = ui.Button("◀ Prev",  width=90,  clicked_fn=self._on_prev)
            self._btn_next   = ui.Button("Next ▶",  width=90,  clicked_fn=self._on_next)
            self._btn_random = ui.Button("Random",  width=75,  clicked_fn=self._on_random)
            ui.Spacer(width=6)
            ui.Label("Index", width=40)
            ui.IntField(model=self._m_index, width=62)
            self._btn_load   = ui.Button("Load",    width=60,  clicked_fn=self._on_load)
        with ui.HStack(spacing=6, height=0):
            ui.Button("Shuffle", width=90,  clicked_fn=self._on_shuffle)
            ui.Button("Sort A-Z", width=80, clicked_fn=self._on_sort)
            ui.Spacer(width=8)
            self._lbl_shuffle = ui.Label("order: sorted", style={"color": 0xFFAAAAAA})
        self._lbl_file = ui.Label("—", word_wrap=True, style={"color": 0xFFCCCCCC})

    def _section_camera(self) -> None:
        with ui.VStack(spacing=4):
            with ui.HStack(spacing=6, height=0):
                ui.Label("Override path", width=110,
                         tooltip="If set, use this cameras.json directly instead of searching.")
                ui.StringField(model=self._m_override, width=ui.Fraction(1))
            for i, (label, tip) in enumerate([
                ("Pattern 1", "e.g.  geom_optim/output/cameras.json"),
                ("Pattern 2", "e.g.  cameras.json"),
                ("Pattern 3", "Optional extra search pattern."),
            ]):
                with ui.HStack(spacing=6, height=0):
                    ui.Label(label, width=70, tooltip=tip)
                    ui.StringField(model=self._m_pat[i], width=ui.Fraction(1))
            with ui.HStack(spacing=6, height=0):
                ui.CheckBox(model=self._m_rot_w2c, width=20)
                ui.Label("Rotation is W→C", width=140,
                         tooltip="Transpose the rotation matrix (world-to-camera → camera-to-world).")
                ui.CheckBox(model=self._m_cv_axes, width=20)
                ui.Label("OpenCV→USD axes", width=130,
                         tooltip="Flip +Y-down/+Z-fwd to +Y-up/-Z-fwd for OpenCV-convention cameras.")
                ui.CheckBox(model=self._m_swap_yz, width=20)
                ui.Label("Swap world Y/Z",
                         tooltip="Permute world Y and Z axes on both rotation and position.")

    def _section_status(self) -> None:
        with ui.HStack(spacing=6, height=0):
            ui.Label("cameras.json:", width=106)
            self._lbl_cam_json = ui.Label("—", word_wrap=True, style={"color": 0xFFAAAAAA})
        self._lbl_status = ui.Label("Ready.", word_wrap=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str) -> None:
        if self._lbl_status is not None:
            try:
                self._lbl_status.text = msg
            except Exception:
                pass

    def _set_cam_json_label(self, path: str) -> None:
        if self._lbl_cam_json is not None:
            try:
                self._lbl_cam_json.text = path or "—"
            except Exception:
                pass

    def _update_file_label(self) -> None:
        n = len(self._state.files)
        if self._lbl_count is not None:
            try:
                self._lbl_count.text = f"{n} files"
            except Exception:
                pass
        cur = ""
        if 0 <= self._state.index < n:
            cur = self._state.files[self._state.index]
        if self._lbl_file is not None:
            try:
                base = os.path.basename(cur) if cur else "—"
                self._lbl_file.text = f"[{self._state.index}/{max(n - 1, 0)}]  {base}\n{cur}"
            except Exception:
                pass
        try:
            self._m_index.set_value(self._state.index)
        except Exception:
            pass

    def _clamp_index(self) -> None:
        n = len(self._state.files)
        self._state.index = max(0, min(n - 1, self._state.index)) if n else 0

    def _set_nav_enabled(self, enabled: bool) -> None:
        for btn in (self._btn_prev, self._btn_next, self._btn_load, self._btn_random):
            if btn is not None:
                try:
                    btn.enabled = enabled
                except Exception:
                    pass

    def _get_patterns(self) -> List[str]:
        out = []
        for m in self._m_pat:
            try:
                p = m.get_value_as_string().strip()
                if p:
                    out.append(p)
            except Exception:
                pass
        return out

    def _persist(self) -> None:
        try:
            s = self._s
            s.set(_KEY_FOLDER,    self._m_folder.get_value_as_string())
            s.set(_KEY_RECURSIVE, self._m_recursive.get_value_as_bool())
            s.set(_KEY_ROT_W2C,   self._m_rot_w2c.get_value_as_bool())
            s.set(_KEY_CV_AXES,   self._m_cv_axes.get_value_as_bool())
            s.set(_KEY_SWAP_YZ,   self._m_swap_yz.get_value_as_bool())
            s.set(_KEY_OVERRIDE,  self._m_override.get_value_as_string())
            for i, key in enumerate([_KEY_PAT0, _KEY_PAT1, _KEY_PAT2]):
                s.set(key, self._m_pat[i].get_value_as_string())
        except Exception:
            pass

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_browse(self) -> None:
        if not _HAS_FILEPICKER:
            self._set_status("File picker unavailable — type the path manually.")
            return
        if self._picker is not None:
            try:
                self._picker.show()
                return
            except Exception:
                self._picker = None

        def _apply(filename: str, dirname: str) -> None:
            folder = dirname or os.path.dirname(filename) or filename
            try:
                self._m_folder.set_value(folder)
            except Exception:
                pass
            try:
                self._picker.hide()
            except Exception:
                pass

        def _cancel(_f: str, _d: str) -> None:
            try:
                self._picker.hide()
            except Exception:
                pass

        try:
            self._picker = _FilePickerDialog(
                "Select USDZ Folder",
                allow_multi_selection=False,
                apply_button_label="Select Folder",
                click_apply_handler=_apply,
                click_cancel_handler=_cancel,
            )
            self._picker.show()
        except Exception as exc:
            self._set_status(f"Picker error: {exc}")

    def _on_scan(self) -> None:
        folder = ""
        try:
            folder = self._m_folder.get_value_as_string().strip()
        except Exception:
            pass

        recursive = False
        try:
            recursive = self._m_recursive.get_value_as_bool()
        except Exception:
            pass

        # Resolve to an absolute path so the status message is unambiguous.
        resolved = os.path.abspath(os.path.expanduser(folder)) if folder else ""

        if not folder:
            self._set_status("Enter a folder path first.")
            return

        if not os.path.isdir(resolved):
            self._set_status(f"Not a directory: {resolved}")
            return

        files = _scan_usdz(folder, recursive)
        self._state.files = files
        self._state.index = 0
        self._state.shuffled = False
        if self._lbl_shuffle is not None:
            try:
                self._lbl_shuffle.text = "order: sorted"
            except Exception:
                pass
        self._update_file_label()
        if not files:
            mode = "recursively" if recursive else "non-recursively"
            self._set_status(f"No .usdz files found ({mode}) in: {resolved}")
        else:
            self._set_status(f"Found {len(files)} file(s) in: {resolved}")
            self._persist()

    def _on_shuffle(self) -> None:
        if not self._state.files:
            self._set_status("Scan a folder first.")
            return
        random.shuffle(self._state.files)
        self._state.index = 0
        self._state.shuffled = True
        if self._lbl_shuffle is not None:
            try:
                self._lbl_shuffle.text = "order: shuffled"
            except Exception:
                pass
        self._update_file_label()
        self._set_status(f"Shuffled {len(self._state.files)} files.")

    def _on_sort(self) -> None:
        if not self._state.files:
            self._set_status("Scan a folder first.")
            return
        self._state.files.sort()
        self._state.index = 0
        self._state.shuffled = False
        if self._lbl_shuffle is not None:
            try:
                self._lbl_shuffle.text = "order: sorted"
            except Exception:
                pass
        self._update_file_label()
        self._set_status("Sorted alphabetically.")

    def _sync_index_from_field(self) -> None:
        try:
            self._state.index = int(self._m_index.get_value_as_int())
        except Exception:
            return
        self._clamp_index()
        self._update_file_label()

    def _on_prev(self) -> None:
        if not self._state.files:
            self._set_status("Scan a folder first.")
            return
        self._state.index -= 1
        self._clamp_index()
        self._update_file_label()
        self._on_load()

    def _on_next(self) -> None:
        if not self._state.files:
            self._set_status("Scan a folder first.")
            return
        self._state.index += 1
        self._clamp_index()
        self._update_file_label()
        self._on_load()

    def _on_random(self) -> None:
        omni.log.warn(f"Random index: {self._state.index}")
        if not self._state.files:
            self._set_status("Scan a folder first.")
            return
        self._state.index = random.randint(0, len(self._state.files) - 1)
        self._update_file_label()
        self._on_load()

    def _on_load(self) -> None:
        if not self._state.files:
            self._set_status("Scan a folder first.")
            return
        omni.log.warn(f"File list: {self._state.files}")
        omni.log.warn(f"Clamping index: {self._state.index}")
        omni.log.warn(f"Loading file: {self._state.files[self._state.index]}")
        self._clamp_index()
        path = self._state.files[self._state.index]
        n = len(self._state.files)
        idx_tag = f"{self._state.index}/{max(n - 1, 0)}"

        # Fixed axis/orientation convention on every load (Matrix-3D / DimensionX).
        preset = _SCENE_ORIENT_PRESET
        force_z = _FORCE_Z_UP
        rot_w2c = False
        cv_axes = False
        swap_yz = False
        try:
            self._m_rot_w2c.set_value(rot_w2c)
            self._m_cv_axes.set_value(cv_axes)
            self._m_swap_yz.set_value(swap_yz)
        except Exception:
            pass
        override = ""
        try:
            override = self._m_override.get_value_as_string().strip()
        except Exception:
            pass
        patterns = self._get_patterns()

        self._pending_load = {
            "path": path, "idx_tag": idx_tag,
            "abs_url": os.path.normcase(os.path.abspath(path)),
            "preset": preset, "force_z": force_z,
            "rot_w2c": rot_w2c, "cv_axes": cv_axes, "swap_yz": swap_yz,
            "override": override, "patterns": patterns,
        }

        self._set_nav_enabled(False)
        self._set_cam_json_label("—")
        self._set_status(f"Loading [{idx_tag}]: {os.path.basename(path)} …")

        # Subscribe to the stage event stream BEFORE opening the stage so we
        # never miss the OPENED event.  The subscription object must stay alive
        # (assigned to self._stage_sub) — dropping it cancels the subscription.
        self._stage_sub = None  # cancel any previous subscription first
        try:
            self._stage_sub = (
                omni.usd.get_context()
                .get_stage_event_stream()
                .create_subscription_to_pop(
                    self._on_stage_event, name="usdz_folder_browser_load"
                )
            )
            omni.log.warn(f"Subscribed to stage events: {self._stage_sub}")
        except Exception as exc:
            self._set_status(f"Could not subscribe to stage events: {exc}")
            self._set_nav_enabled(True)
            omni.log.warn(f"Could not subscribe to stage events: {exc}")
            return

        try:
            _unload_stage()
            _open_stage(path)
        except Exception as exc:
            self._stage_sub = None
            self._pending_load = None
            self._set_status(f"Open stage failed: {exc}")
            self._set_nav_enabled(True)

    def _on_stage_event(self, event) -> None:
        """Called by Kit's stage event stream on every stage change."""
        import omni.usd

        pending = self._pending_load
        if pending is None:
            return

        et = event.type
        opened = int(omni.usd.StageEventType.OPENED)
        failed = int(getattr(omni.usd.StageEventType, "OPEN_FAILED", -1))

        if et == failed:
            self._stage_sub = None
            self._pending_load = None
            self._set_status("Stage open failed.")
            self._set_nav_enabled(True)
            return

        if et != opened:
            return

        # Verify this OPENED event is for the stage we requested, not for the
        # empty stage created during unload.
        try:
            stage_url = omni.usd.get_context().get_stage_url() or ""
            stage_url = os.path.normcase(os.path.abspath(stage_url))
            if stage_url != pending["abs_url"]:
                return  # intermediate stage (empty stage from unload) — ignore
        except Exception:
            pass  # if we can't verify, proceed anyway

        # Correct stage is now loaded — unsubscribe and apply post-load work.
        self._stage_sub = None
        self._pending_load = None
        self._post_load(pending)
        omni.log.warn(f"Post-load complete")

    def _post_load(self, p: dict) -> None:
        """Apply orientation fix and camera init after the stage is fully open."""
        try:
            orient_ok = _apply_orientation(p["preset"], p["force_z"])

            cam_json = _resolve_cameras_json(p["path"], p["patterns"], p["override"])
            omni.log.warn(f"Resolved cameras.json: {cam_json}")
            omni.log.warn(f"p['path']: {p['path']}")
            omni.log.warn(f"p['patterns']: {p['patterns']}")
            omni.log.warn(f"p['override']: {p['override']}")
            self._set_cam_json_label(cam_json or "not found")

            cam_tag = "no cameras.json"
            if cam_json:
                cam0 = _load_camera0(cam_json)
                if cam0 and _apply_camera(
                    cam0,
                    p["rot_w2c"],
                    p["cv_axes"],
                    p["swap_yz"],
                    scene_preset=p["preset"],
                ):
                    cam_tag = "camera OK"
                else:
                    cam_tag = "camera FAILED"

            orient_tag = f"orient: {'OK' if orient_ok else 'FAIL'}"
            self._set_status(
                f"[{p['idx_tag']}] {os.path.basename(p['path'])}  |  {orient_tag}  |  {cam_tag}"
            )
            _sync_scene_recorder_paths(p["path"])
            self._persist()
        except Exception as exc:
            self._set_status(f"Post-load error: {exc}")
        finally:
            self._set_nav_enabled(True)
