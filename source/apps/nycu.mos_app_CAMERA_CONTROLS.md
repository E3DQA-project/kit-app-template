# MOS App — Camera Controls Report

**App:** `nycu.mos_app.kit`  
**Generated:** 2026-07-07  
**Scope:** Default camera control handling (no code modifications)

---

## Architecture Overview

Camera behavior in MOS App comes from **three layers**:

1. **NVIDIA Kit SDK extensions** (loaded via `.kit` dependencies) — live mouse/keyboard/gamepad navigation
2. **App-level `.kit` settings** — fly mode, speed tuning, and explicit gamepad enablement
3. **Custom extensions** — initial camera pose, reset, and workflow UI (not live navigation input)

```
nycu.mos_app.kit  (template: omni.usd_viewer)
│
├── Kit SDK: omni.kit.manipulator.camera     → Live navigation (WASD, mouse, gamepad)
├── Kit SDK: omni.kit.viewport.window        → Viewport host
├── nycu.my_usd_viewer_setup_extension       → Viewport-only layout, menu hidden
└── nycu.mos_app_extension                   → Nav presets, cameras.json init, camera reset (R)
```

**Not used:** `camera_controls`, `usdz_folder_browser`, `scene_recorder`, or `metric_sliders`. MOS App inlines equivalent logic inside `nycu.mos_app_extension`.

---

## 1. App Config: `nycu.mos_app.kit`

### Kit SDK Dependencies (Live Navigation + Viewport)

| Dependency | Role |
|------------|------|
| `omni.kit.manipulator.camera` | Core camera manipulator (WASD fly, mouse look, **gamepad**) |
| `omni.kit.viewport.window` | Viewport window |
| `omni.kit.viewport.utility` | Viewport API helpers (used by MOS extension for camera activation) |
| `omni.kit.manipulator.selection` | Selection manipulator (minimal editor chrome) |

Unlike E3DQA Scene Viewer, MOS App does **not** load `omni.kit.viewport.menubar.camera`, `omni.kit.viewport.scene_camera_model`, or other editor viewport menus. It is a viewport-only USD Viewer app.

**Relevant lines in `.kit`:**

```toml
"omni.kit.manipulator.camera" = {}
"omni.kit.viewport.utility" = {}
"omni.kit.viewport.window" = {}
"nycu.my_usd_viewer_setup_extension" = { order = 1000 }
"nycu.mos_app_extension" = { order = 1100 }
```

### Custom Extension Dependencies

MOS App depends on exactly two custom extensions — neither is named `camera_controls`:

| Extension | Role in camera stack |
|-----------|---------------------|
| `nycu.my_usd_viewer_setup_extension` | Loads viewport-only layout; hides menu bar; sets viewport to fill frame |
| `nycu.mos_app_extension` | Nav defaults, `cameras.json` placement, initial-pose capture, **R** reset |

### Persistent Camera / Navigation Settings

```toml
[settings.persistent.app]
viewport.autoFrame.mode = "first_open"
viewport.defaults.tickRate = 60
viewport.noPadding = true

[settings.persistent.app.viewport]
camVelocityMin = 0.01
camMoveVelocity = 1.0

[settings.persistent.app.viewport.manipulator.camera]
flyAcceleration = 1000.0
flyDampening = 10.0
moveAcceleration = 1000.0
moveDampening = 10.0

[settings.persistent.app.omniverse]
gamepadCameraControl = true  # DualShock / gamepad fly + look (via omni.kit.manipulator.camera)

[settings.persistent.exts]
"omni.kit.window.sequencer".useSequencerCamera = false  # Free fly nav; don't lock viewport to sequencer
```

| Setting | Effect |
|---------|--------|
| `camVelocityMin = 0.01` | Minimum move speed |
| `camMoveVelocity = 1.0` | Default move speed (higher than E3DQA's 0.01 default) |
| `flyAcceleration / flyDampening` | Fly-mode responsiveness |
| `moveAcceleration / moveDampening` | Move-mode responsiveness |
| **`gamepadCameraControl = true`** | **Enables Kit gamepad → camera mapping** |
| `useSequencerCamera = false` | Prevents sequencer from hijacking the viewport camera |

### Runtime Navigation Defaults (Non-Persistent)

```toml
[settings.exts]
"omni.kit.window.viewport".showContextMenu = false  # Disable context menu, viewer not editor.

[settings]
app.viewport.currentTool = "navigation"
exts."omni.kit.viewport.navigation.core".activeOperation = "fly"
exts."omni.kit.viewport.navigation.camera_manipulator".defaultOperation = "fly"
guide.grid.visible = false
```

| Setting | Effect |
|---------|--------|
| `app.viewport.currentTool = "navigation"` | Navigation tool active |
| `activeOperation = "fly"` | Fly mode (WASD + mouse) |
| `defaultOperation = "fly"` | Fly persists as default |
| `showContextMenu = false` | RMB free for look/drag (not context menu) |

### Viewport Chrome Hidden

```toml
[settings.app.viewport.defaults]
fillViewport = true
guide.grid.visible = false
guide.axis.visible = false
hud.visible = false
scene.cameras.visible = false
scene.lights.visible = false
```

Minimal on-screen chrome — appropriate for a controller-first evaluation UI.

---

## 2. Setup Extension: `nycu.my_usd_viewer_setup_extension`

**Source:** `source/extensions/nycu.my_usd_viewer_setup_extension/`

This extension does **not** handle navigation input. It configures the viewport shell:

- Hides the main menu bar
- Loads `layouts/default.json` (viewport-only, no stage tree / property editor)
- Sets viewport `fill_frame = True` after layout load

Camera controls pass through to the Kit manipulator inside the viewport window it lays out.

---

## 3. MOS App Extension: `nycu.mos_app_extension`

**Source:** `source/extensions/nycu.mos_app_extension/nycu/mos_app_extension/extension.py`

This is the primary custom layer for camera-related behavior. It replaces what E3DQA splits across `camera_controls` and `usdz_folder_browser`.

### 3.1 Navigation Defaults (mirrors `camera_controls`)

On startup and after every scene load, `_apply_nav_defaults()` writes:

| Carb Path | Value | Purpose |
|-----------|-------|---------|
| `/persistent/app/viewport/camVelocityMin` | `0.01` | Min speed |
| `/app/viewport/currentTool` | `"navigation"` | Navigation tool |
| `/exts/omni.kit.viewport.navigation.core/activeOperation` | `"fly"` | Fly mode |
| `/exts/omni.kit.viewport.navigation.camera_manipulator/defaultOperation` | `"fly"` | Default fly |
| `/exts/omni.kit.window.viewport/showContextMenu` | `False` | RMB for look |
| **`/persistent/app/omniverse/gamepadCameraControl`** | **`True`** | **Gamepad camera on** |
| `/persistent/exts/omni.kit.window.sequencer/useSequencerCamera` | `False` | Free-fly, not sequencer-locked |

Comment in source: `# carb.settings paths for camera/navigation (mirror camera_controls).`

### 3.2 Initial Camera Pose (mirrors `usdz_folder_browser`)

After each USDZ load, `_post_load()`:

1. Applies scene orientation preset (`rx-90`, force Z-up) — same as E3DQA defaults
2. Walks up directory tree to find `cameras.json` (patterns: `geom_optim/output/cameras.json`, `cameras.json`)
3. Creates `/BrowserCamera` from camera index 0 via `_apply_camera_from_json()`
4. Activates `/BrowserCamera` in the viewport
5. Captures the initial transform for later reset

### 3.3 Camera Reset (keyboard only in current code)

| Input | Action | State |
|-------|--------|-------|
| **R** | Reset camera to initial post-load pose | `NAVIGATING` only |
| **Enter** | Open scoring panel | `NAVIGATING` |
| **Esc** | Close scoring panel | `SCORING` |

Reset restores `/BrowserCamera` transform and re-activates it in the viewport. It does **not** reload the USDZ.

**Keyboard subscription:** The extension uses `carb.input.subscribe_to_keyboard_events()` — there is **no** `subscribe_to_gamepad_events()` in the current implementation.

### 3.4 What the extension does NOT do

- Does not implement live WASD/mouse/gamepad input (delegated to Kit SDK)
- Does not provide speed-tuning sliders (unlike E3DQA's `camera_controls` window)
- Does not record/replay camera paths (no `scene_recorder`)

---

## 4. DualShock 4 Support — Why and How

### Explicitly enabled in this app (unlike E3DQA)

MOS App **intentionally** enables gamepad camera control in two places:

1. **`.kit` file** — persistent default:

   ```toml
   [settings.persistent.app.omniverse]
   gamepadCameraControl = true  # DualShock / gamepad fly + look (via omni.kit.manipulator.camera)
   ```

2. **Runtime** — re-applied on startup and after every scene load:

   ```python
   s.set(_S_GAMEPAD, True)  # /persistent/app/omniverse/gamepadCameraControl
   ```

### How DS4 navigation actually works

There is **no DualShock-specific code** in this repository. DS4 support comes from:

1. **`omni.kit.manipulator.camera`** — Kit SDK extension with built-in generic gamepad mappings under `/exts/omni.kit.manipulator.camera/gamePad/*`:
   - Left stick → fly (move)
   - Right stick → look
   - Triggers → fly Y (vertical)
   - D-pad → fly
   - Shoulder buttons → speed modifiers

2. **`gamepadCameraControl = true`** — global persistent toggle that tells the manipulator to consume gamepad input for camera movement.

3. **OS-level gamepad driver** — on Linux, a DualShock 4 appears as a standard gamepad (e.g. via `hid-playstation` or `ds4drv`). Kit reads it through `carb.input` like any other controller.

### PRD vs. current implementation

The PRD (`nycu.mos_app_PRD.md`) describes a full DS4 workflow:

| Action | PRD (DS4) | Current code |
|--------|-----------|--------------|
| Navigate viewport | Sticks, L2/R2 | ✅ Kit SDK (when `gamepadCameraControl = true`) |
| Reset camera | Triangle | ❌ Not implemented — **R** keyboard only |
| Open scoring | Cross (X) | ❌ Not implemented — **Enter** keyboard only |
| Close scoring | Circle | ❌ Not implemented — **Esc** keyboard only |
| Scoring panel D-pad | Up/Down/Left/Right | ❌ Not implemented |

The PRD references a planned `navigation_controller.py` module; the shipped code is a single `extension.py` with keyboard routing only. **DS4 sticks work for camera fly/look; DS4 buttons for workflow actions are specified but not yet coded.**

---

## 5. Comparison with E3DQA Scene Viewer

| Aspect | E3DQA Scene Viewer | MOS App |
|--------|-------------------|---------|
| Base template | `kit_base_editor` | `omni.usd_viewer` |
| `camera_controls` extension | ✅ Loaded | ❌ Not used (logic inlined in MOS extension) |
| `usdz_folder_browser` | ✅ Loaded | ❌ Not used (camera init inlined) |
| `gamepadCameraControl` | ❌ Not set | ✅ **`true` in `.kit` + runtime** |
| Fly mode defaults | `.kit` + `camera_controls` | `.kit` + `nycu.mos_app_extension` |
| Camera reset | Manual only | **R** key → initial pose |
| Speed tuning UI | Camera Controls window | None (fixed `.kit` values) |
| DS4 navigation | Accidental (Kit persistent) | **Intentional** |
| DS4 workflow buttons | N/A | PRD only; not in code yet |

---

## 6. Summary Table

| Component | Role in Camera Controls | Loaded by Default? |
|-----------|-------------------------|-------------------|
| `omni.kit.manipulator.camera` | Core navigation (WASD, mouse, gamepad) | Yes |
| `omni.kit.viewport.navigation.*` | Fly operation mode | Yes (transitive) |
| `omni.kit.viewport.window` | Viewport host | Yes |
| `.kit` fly/navigation settings | Default to fly mode | Yes |
| `.kit` `gamepadCameraControl = true` | Enable gamepad camera | **Yes** |
| `.kit` manipulator speed settings | Accel/damp/velocity | Yes |
| **`nycu.mos_app_extension`** | Nav presets, cameras.json, reset | **Yes** |
| `nycu.my_usd_viewer_setup_extension` | Viewport-only layout | Yes |
| **`camera_controls`** | — | **No** |
| `usdz_folder_browser` | — | No |
| `scene_recorder` | — | No |
| DualShock 4 (sticks) | Via Kit SDK gamepad path | Yes (explicit) |
| DualShock 4 (buttons) | PRD spec only | Not implemented |

---

## Related Files

| File | Relevance |
|------|-----------|
| `source/apps/nycu.mos_app.kit` | Dependencies, gamepad flag, nav/speed settings |
| `source/apps/nycu.mos_app_PRD.md` | Full DS4 input spec (PRD) |
| `source/extensions/nycu.mos_app_extension/nycu/mos_app_extension/extension.py` | Nav defaults, camera init, reset, keyboard routing |
| `source/extensions/nycu.my_usd_viewer_setup_extension/nycu/my_usd_viewer_setup_extension/setup.py` | Viewport layout |
| `source/apps/nycu.e3dqa_scene_viewer_CAMERA_CONTROLS.md` | E3DQA counterpart analysis |
| `source/extensions/camera_controls/` | Reference implementation (not a MOS dependency) |
