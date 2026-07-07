# E3DQA Scene Viewer — Camera Controls Report

**App:** `nycu.e3dqa_scene_viewer.kit`  
**Generated:** 2026-07-07  
**Scope:** Default camera control handling (no code modifications)

---

## Architecture Overview

Camera behavior in this app comes from **three layers**:

1. **NVIDIA Kit SDK extensions** (loaded via `.kit` dependencies) — actual mouse/keyboard/gamepad input and fly/orbit logic
2. **App-level `.kit` settings** — default mode (navigation + fly)
3. **Custom extensions** — tuning UI, initial pose, recording/replay

```
nycu.e3dqa_scene_viewer.kit
│
├── Kit SDK: omni.kit.manipulator.camera     → Live navigation (WASD, mouse, optional gamepad)
├── Kit SDK: omni.kit.viewport.*               → Viewport window + camera menus
├── camera_controls extension                  → Preset fly mode + speed sliders
├── usdz_folder_browser extension              → Initial camera pose from cameras.json
└── scene_recorder extension                   → Record/replay camera paths
```

---

## 1. App Config: `nycu.e3dqa_scene_viewer.kit`

### Kit SDK Dependencies (Live Navigation + Viewport)

These are the built-in extensions that actually handle interactive camera control:

| Dependency | Role |
|------------|------|
| `omni.kit.manipulator.camera` | Core camera manipulator (WASD fly, mouse look, optional gamepad) |
| `omni.kit.viewport.window` | Viewport that hosts the manipulator |
| `omni.kit.viewport.menubar.camera` | "View from camera" UI |
| `omni.kit.viewport.scene_camera_model` | Keeps scene camera UI in sync |

`omni.kit.viewport.navigation.core` and `omni.kit.viewport.navigation.camera_manipulator` are **not listed explicitly**, but they are pulled in transitively by the manipulator/viewport stack and configured via settings below.

**Relevant lines in `.kit`:**

```toml
"omni.kit.manipulator.camera" = {}  # Load the camera-manipulator (navigation)
"omni.kit.viewport.menubar.camera" = {}  # Load the view-from-camera menu
"omni.kit.viewport.scene_camera_model" = {} # Sync camera to scene UI
"omni.kit.viewport.window" = {}  # Load the actual ViewportWindow extension
```

### Custom Extension Dependencies

```toml
"usdz_folder_browser" = {}   # USDZ folder scanner, load/unload, orientation fix, camera pose init
"metric_sliders" = {}         # QA rating panel (0–5 per dimension, persisted per stage URL)
"camera_controls" = {}        # WASD fly navigation presets and speed sliders
"scene_recorder" = {}         # Live camera-path recording, trajectory JSON, replay, and video export
```

### App-Level Navigation Defaults

```toml
[settings.persistent.app]
viewport.autoFrame.mode = "first_open"  # Auto frame the first time the viewport is opened

[settings]
app.viewport.currentTool = "navigation"
exts."omni.kit.viewport.navigation.core".activeOperation = "fly"
exts."omni.kit.viewport.navigation.camera_manipulator".defaultOperation = "fly"
```

| Setting | Effect |
|---------|--------|
| `app.viewport.currentTool = "navigation"` | Selects the navigation tool (not select/transform) |
| `activeOperation = "fly"` | Fly mode (WASD + mouse look) |
| `defaultOperation = "fly"` | Fly stays the default nav operation |
| `viewport.autoFrame.mode = "first_open"` | Auto-frames scene on first viewport open |

These mirror what `camera_controls` applies at runtime, so fly mode is active even before the custom extension starts.

---

## 2. Custom Extension: `camera_controls`

**Source:** `source/extensions/camera_controls/`  
**Loaded by default:** Yes — listed in `[dependencies]`

### Does the app rely on it?

**Yes.** The app explicitly depends on the local `camera_controls` extension and loads it on every startup.

What it does **not** do: implement input handling. It only writes Kit settings and exposes a tuning panel on top of the SDK manipulator.

### Settings Applied on Startup

| Carb Path | Purpose |
|-----------|---------|
| `/persistent/app/viewport/camMoveVelocity` | Move speed |
| `/persistent/app/viewport/camVelocityMin/Max` | Speed bounds |
| `/persistent/app/viewport/manipulator/camera/moveAcceleration` | Move accel |
| `/persistent/app/viewport/manipulator/camera/flyDampening` | Look/fly damping |
| `/app/viewport/currentTool` | `"navigation"` |
| `/exts/omni.kit.viewport.navigation.core/activeOperation` | `"fly"` |
| `/exts/omni.kit.viewport.navigation.camera_manipulator/defaultOperation` | `"fly"` |
| `/exts/omni.kit.window.viewport/showContextMenu` | `false` (RMB free for look/drag) |

### UI

Window title: **"Camera Controls"** — sliders for Move Speed, Speed Min/Max, Move Accel, Look/Fly Damp, plus Apply and Reapply Preset buttons.

**Conclusion:** `camera_controls` is a preset/tuning layer on top of Kit's built-in manipulator, not a replacement for it. Without it, fly mode would still work from the `.kit` settings alone (lines 96–98).

---

## 3. `usdz_folder_browser` — Initial Camera Pose, Not Navigation

**Source:** `source/extensions/usdz_folder_browser/`

This extension sets **where the camera starts**, not how you move it:

- Resolves `cameras.json` from dataset layout (override path or walk-up search)
- Creates `/BrowserCamera` prim with position/rotation from camera index 0
- Applies scene orientation presets (e.g. OpenCV Y-down → Z-up)
- Activates the camera in the viewport via `omni.kit.viewport.utility`

After loading a USDZ, it resolves `cameras.json`, creates `/BrowserCamera`, and activates it. That is **pose initialization**, separate from WASD/fly controls.

---

## 4. `scene_recorder` — Record/Replay, Not Default Navigation

**Source:** `source/extensions/scene_recorder/`

Loaded by default, but only for:

- Sampling the active viewport camera while you navigate
- Saving/replaying trajectories as JSON
- Video export via `omni.kit.capture.viewport` / `omni.kit.window.movie_capture`

It reads the camera pose from the viewport; it does not define how you navigate.

---

## 5. DualShock 4 — Not Configured in This App

There is **no** DualShock/gamepad configuration anywhere in `nycu.e3dqa_scene_viewer.kit` or its custom extensions. A repo-wide search for `gamepad`, `dualshock`, and `gamepadCameraControl` in the E3DQA app finds nothing.

The E3DQA spec (`e3dqa_scene_viewer_SPECS.md`) describes **WASD fly navigation only**.

### Where DualShock 4 *Is* Configured

DualShock 4 is explicitly configured in the separate **MOS App**, not E3DQA:

**`nycu.mos_app.kit`:**

```toml
[settings.persistent.app.omniverse]
gamepadCameraControl = true  # DualShock / gamepad fly + look (via omni.kit.manipulator.camera)
```

**`nycu.mos_app_extension/extension.py`:**

```python
_S_GAMEPAD = "/persistent/app/omniverse/gamepadCameraControl"
# ... sets to True at runtime
```

### If a DS4 Still Works in E3DQA Scene Viewer

That would come from **Kit SDK built-ins**, not from this app's config:

1. **`omni.kit.manipulator.camera`** includes generic gamepad support via `/exts/omni.kit.manipulator.camera/gamePad/*` settings (left stick fly, right stick look, triggers, d-pad, etc.).
2. The global toggle is **`/persistent/app/omniverse/gamepadCameraControl`**. Because it is under `/persistent/`, it can remain `true` from:
   - the viewport hamburger menu ("Gamepad Camera Control"),
   - another Kit app (e.g. MOS App),
   - or a prior session.
3. On Linux, a DualShock 4 is usually exposed as a standard gamepad (often via `ds4drv` / `hid-playstation`), so Kit treats it like any other controller — there is **no DS4-specific code** in this repo for E3DQA.

**Bottom line:** E3DQA Scene Viewer does **not** intentionally target DualShock 4. If you see DS4 input, it is almost certainly Kit's optional gamepad camera path via `omni.kit.manipulator.camera`, possibly left enabled by persistent settings — not something declared in `nycu.e3dqa_scene_viewer.kit`.

---

## Summary Table

| Component | Role in Camera Controls | Loaded by Default? |
|-----------|-------------------------|-------------------|
| `omni.kit.manipulator.camera` | Core navigation input (WASD, mouse, optional gamepad) | Yes |
| `omni.kit.viewport.navigation.*` | Fly/orbit operation mode | Yes (transitive) |
| `omni.kit.viewport.window` | Viewport host | Yes |
| `.kit` fly/navigation settings | Default to fly mode | Yes |
| **`camera_controls`** | Presets + speed/accel UI | **Yes** |
| `usdz_folder_browser` | Initial camera pose from `cameras.json` | Yes |
| `scene_recorder` | Record/replay paths | Yes (secondary) |
| DualShock 4 | Not configured | No explicit support |

---

## Related Files

| File | Relevance |
|------|-----------|
| `source/apps/nycu.e3dqa_scene_viewer.kit` | App dependencies and navigation defaults |
| `source/apps/e3dqa_scene_viewer_SPECS.md` | Full app specification |
| `source/extensions/camera_controls/camera_controls/extension.py` | Fly preset + tuning UI |
| `source/extensions/usdz_folder_browser/usdz_folder_browser/extension.py` | Initial camera pose |
| `source/extensions/scene_recorder/scene_recorder/camera_recorder.py` | Live pose sampling |
| `source/apps/nycu.mos_app.kit` | Reference: explicit DS4/gamepad config |
