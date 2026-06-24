# E3DQA Scene Viewer — Specification

**Kit file:** `nycu.e3dqa_scene_viewer.kit`  
**Kit SDK:** 110.0.0+feature.276876.4a5123f4.gl  
**Version:** 0.1.0

---

## 1. Purpose

The E3DQA Scene Viewer is a GPU-accelerated USDZ inspection and quality-assessment application built on NVIDIA Omniverse Kit. It is designed for rapid evaluation of 3D reconstructed scenes (e.g. 3D Gaussian Splatting outputs exported as USDZ), supporting:

- Batch traversal of a folder of `.usdz` files (previous / next / jump-to-index)
- Automatic camera initialisation from dataset-supplied `cameras.json` files
- Scene orientation correction for OpenCV-convention reconstruction outputs
- Per-file manual quality scoring (4 dimensions, 0–5 integer scale)
- WASD fly-navigation tuning for comfortable scene review

---

## 2. Application Architecture

```
nycu.e3dqa_scene_viewer.kit
│
├── [Kit base editor]          Viewport, stage tree, property editor, menus, toolbars
│   ├── omni.kit.viewport.window
│   ├── omni.kit.window.stage
│   ├── omni.kit.window.property
│   ├── omni.kit.window.console
│   ├── omni.kit.window.content_browser
│   └── omni.hydra.rtx              (RTX renderer)
│
├── [E3DQA custom extensions]
│   ├── usdz_folder_browser         Scene loading and camera init
│   ├── metric_sliders              QA scoring panel
│   └── camera_controls             WASD navigation presets
│
└── [Supporting runtime]
    ├── omni.graph.*                Action graph / script nodes
    ├── omni.physx.*                Physics runtime
    ├── omni.warp.core              GPU scripting
    └── omni.usd.metrics.assembler  Unit/scale metadata
```

---

## 3. Custom Extensions

### 3.1 `usdz_folder_browser`

**Window title:** "USDZ Folder Browser"  
**Source:** `source/extensions/usdz_folder_browser/`

#### 3.1.1 Responsibilities

1. Scan a user-supplied directory for `.usdz` files (optionally recursive).
2. Traverse the file list (previous / next / jump-to-index).
3. Before each load, unload the current stage to release VRAM.
4. After loading, apply a scene orientation rotation to `/World`.
5. Locate the nearest `cameras.json` and initialise `/World/BrowserCamera` from camera index 0.
6. Activate the created camera in the viewport.

#### 3.1.2 UI Layout

| Section | Controls |
|---------|----------|
| **FOLDER** | Path field, Browse button (requires `omni.kit.window.filepicker`), Scan button, Recursive checkbox, file count |
| **FILE NAVIGATION** | Previous, Next, Index field, Load button; current file path display |
| **SCENE ORIENTATION** | Preset buttons: None / Rx±90 / Ry±90 / Rz±90; active preset indicator; Force Z-up checkbox |
| **CAMERA INITIALISATION** | Override cameras.json path field; collapsible search-patterns text area; camera convention checkboxes |
| **STATUS** | Resolved cameras.json path; per-load status message |

#### 3.1.3 Scene Orientation Presets

Applied as a `xformOp:transform` on the `/World` prim immediately after stage open.

| Preset | Rotation | Typical use |
|--------|----------|-------------|
| `none` | identity | Scene already correctly oriented |
| `rx-90` | −90° around X | **Default.** OpenCV Y-down world → Z-up (most 3DGS exports) |
| `rx+90` | +90° around X | Z-up world needing Y-up flip |
| `ry±90` | ±90° around Y | 90° horizontal axis mismatch |
| `rz±90` | ±90° around Z | Roll correction |

**Force Z-up** calls `UsdGeom.SetStageUpAxis(stage, 'Z')` before camera initialisation, ensuring consistent behaviour regardless of what the USDZ declares.

#### 3.1.4 Camera Initialisation

Source: a JSON file resolved by one of these methods (highest priority first):

1. **Override path** — the "Override cameras.json" field, used verbatim if the file exists.
2. **Walk-up search** — starting from the loaded USDZ's directory, walk up the directory tree; at each level try each search pattern.

**Default search patterns** (one per line in the UI text area):
```
../../cameras.json
geom_optim/output/cameras.json
```

These patterns are relative to the current ancestor directory being tested, so `geom_optim/output/cameras.json` means `<ancestor>/geom_optim/output/cameras.json`.

**`cameras.json` format** (array of camera objects):
```json
[
  {
    "position": [x, y, z],
    "rotation": [[r00, r01, r02], [r10, r11, r12], [r20, r21, r22]],
    "width": 1920,
    "height": 1080,
    "fx": 1200.0,
    "fy": 1200.0
  },
  ...
]
```
Only `camera[0]` (index 0) is used for initial placement.

**Coordinate convention checkboxes:**

| Checkbox | Default | Effect when enabled |
|----------|---------|---------------------|
| Rotation is W→C | off | Transposes the rotation matrix before use |
| OpenCV → USD axes | on | Applies flip matrix `diag(1, -1, -1)` to camera frame (+Y-down,+Z-fwd → +Y-up,−Z-fwd) |
| Swap world Y/Z | off | Permutes world Y and Z axes on both rotation and position |

**Created USD prim:** `/World/BrowserCamera` (type `Camera`)  
- Focal length derived from `fx` (pixels) and horizontal aperture (20.955 mm default).
- Clipping range: near = `max(0.001, dist/1000)`, far = `max(100, dist*20)`, where `dist` = distance from origin to camera position.

#### 3.1.5 Persistent Settings

All user choices are persisted across restarts via `carb.settings` (stored in Kit's `persistent` settings layer):

| Key | Default | Description |
|-----|---------|-------------|
| `/persistent/exts/usdz_folder_browser/lastFolder` | `""` | Last scanned folder path |
| `/persistent/exts/usdz_folder_browser/recursive` | `false` | Recursive scan toggle |
| `/persistent/exts/usdz_folder_browser/cameraPatterns` | *(two defaults)* | Newline-separated search patterns |
| `/persistent/exts/usdz_folder_browser/sceneOrientPreset` | `"rx-90"` | Active orientation preset |
| `/persistent/exts/usdz_folder_browser/forceZUp` | `true` | Force Z up-axis |
| `/persistent/exts/usdz_folder_browser/rotationIsW2C` | `false` | Rotation is world-to-camera |
| `/persistent/exts/usdz_folder_browser/opencvAxes` | `true` | OpenCV → USD axis conversion |
| `/persistent/exts/usdz_folder_browser/swapYZWorld` | `false` | Swap world Y/Z axes |

#### 3.1.6 Known Limitations

- Only the first camera (`cameras[0]`) is used; multi-camera traversal is not supported.
- No scale/`metersPerUnit` correction. If the USDZ encodes incorrect units, the scene will appear at the wrong scale; a manual `xformOp:scale` on `/World` is required outside this tool.
- The Browse button is only available when `omni.kit.window.filepicker` is loaded (present in the full editor app; absent in minimal configurations).

---

### 3.2 `metric_sliders`

**Window title:** "Metric Sliders"  
**Source:** `source/extensions/metric_sliders/`

#### 3.2.1 Responsibilities

Provide a simple human-in-the-loop QA scoring interface for the currently loaded scene, with per-file persistence.

#### 3.2.2 Metrics (0–5 integer scale)

| Metric | Description |
|--------|-------------|
| Geometric Consistency | Accuracy of 3D geometry relative to the real scene |
| Textural Fidelity | Quality and correctness of surface appearance |
| Volumetric Cleanliness | Absence of floaters, noise, and spurious density |
| Semantic Context Coherence | Completeness and correct representation of scene objects |

#### 3.2.3 Persistence

Scores are stored in a per-user JSON database keyed by the stage URL:

- **Path:** `$XDG_STATE_HOME/metric_sliders/metrics.json` (fallback: `~/.local/state/metric_sliders/metrics.json`)
- **Key:** `omni.usd.get_context().get_stage_url()` (full filesystem path of the loaded USDZ)
- **Format:**
  ```json
  {
    "/path/to/scene.usdz": {
      "saved_at": "2026-06-11T08:00:00+00:00",
      "metrics": {
        "Geometric Consistency": 4,
        "Textural Fidelity": 3,
        "Volumetric Cleanliness": 5,
        "Semantic Context Coherence": 3
      }
    }
  }
  ```

Scores for the current stage are **automatically loaded** on extension startup. Use **Save** after scoring, **Load (current file)** to restore, and **Reset to 0** to clear.

---

### 3.3 `camera_controls`

**Window title:** "Camera Controls"  
**Source:** `source/extensions/camera_controls/`

#### 3.3.1 Responsibilities

Set viewport navigation defaults on startup and provide runtime tuning sliders. Does not affect initial camera position or scene scale.

#### 3.3.2 Defaults Applied on Startup

| Setting | Value | Purpose |
|---------|-------|---------|
| `camVelocityMin` | 0.01 | Prevents camera from stopping completely |
| `currentTool` | `"navigation"` | Activates navigation tool |
| `activeOperation` | `"fly"` | WASD fly mode |
| `defaultOperation` | `"fly"` | Persists fly mode as default |
| `showContextMenu` | `false` | Frees RMB for look/drag |

#### 3.3.3 Tunable Parameters

Move Speed, Speed Min/Max, Move Acceleration, Look/Fly Dampening — all adjustable via sliders and applied immediately on "Apply".

---

## 4. App-Level Settings

### 4.1 Navigation

```toml
app.viewport.currentTool = "navigation"
exts."omni.kit.viewport.navigation.core".activeOperation = "fly"
exts."omni.kit.viewport.navigation.camera_manipulator".defaultOperation = "fly"
guide.grid.visible = false
```

These mirror what `camera_controls` sets at runtime, ensuring fly mode is active even before the extension initialises.

### 4.2 Viewport

```toml
[settings.persistent.app]
viewport.autoFrame.mode = "first_open"   # Kit built-in: auto-frame on first file open
```

Note: `autoFrame` zooms to fit the scene's bounding box. It is distinct from the `cameras.json`-based camera placement in `usdz_folder_browser`, which sets a specific camera pose. If `cameras.json` is found, the explicit pose overrides the auto-frame.

### 4.3 Renderer

```toml
renderer.asyncInit = true          # Non-blocking renderer startup
renderer.gpuEnumeration.glInterop.enabled = false  # Faster startup
rtx.ecoMode.enabled = true
rtx.hydra.mdlMaterialWarmup = true # Pre-warm MDL shaders
app.renderer.skipWhileMinimized = true
```

---

## 5. Dataset Layout

The default `cameras.json` search patterns match the following directory structures:

**Pattern 1: `../../cameras.json`**
```
<scene_root>/
    cameras.json          ← resolved from scene/*/scene.usdz
    scene/
        <variant>/
            scene.usdz
```

**Pattern 2: `geom_optim/output/cameras.json`**
```
<scene_root>/
    geom_optim/
        output/
            cameras.json  ← resolved from <scene_root>/scene.usdz
    scene.usdz
```

Custom patterns can be added in the **Search patterns** collapsible section of the USDZ Folder Browser window. An explicit override path bypasses all pattern matching.

---

## 6. What Is Not Implemented

| Feature | Status | Notes |
|---------|--------|-------|
| Scale / metersPerUnit correction | Not implemented | Add `xformOp:scale` on `/World` once correct factor is known |
| Multi-camera traversal | Not implemented | Only `cameras[0]` is used |
| Batch export of metrics | Not implemented | Metrics DB is a flat JSON; export can be done externally |
| Auto-advance on timer | Not implemented | Load is always manually triggered |
