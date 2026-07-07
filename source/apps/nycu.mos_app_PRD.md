# MOS App — Product Requirements Document

**Kit file:** `nycu.mos_app.kit`  
**Kit SDK:** 110.0.0+feature.276876.4a5123f4.gl  
**Version:** 0.1.0  
**Status:** Draft  
**Date:** 2026-07-07

---

## 1. Summary

MOS App is a viewport-only Omniverse Kit application for **sequential human evaluation of USDZ scenes**. A participant identifies themselves at startup, walks through an ordered scene list defined in JSON, navigates each scene with a DualShock 4 (DS4) controller, submits ordinal quality scores via a toggleable scoring panel, and advances to the next scene.

This PRD defines requirements for a **new extension** (`nycu.mos_app_extension`) wired into `nycu.mos_app.kit`. Existing extensions **must not be modified**:

| Extension | Constraint |
|-----------|------------|
| `nycu.my_usd_viewer_setup_extension` | Read-only; provides viewport layout |
| `nycu.my_usd_viewer_messaging_extension` | Read-only; streaming messaging remains available but is not required for local evaluation |

Reference implementations elsewhere in the repo (not dependencies): `usdz_folder_browser`, `metric_sliders`, `camera_controls`, `e3dqa_scene_viewer_SPECS.md`.

---

## 2. Goals

| ID | Goal |
|----|------|
| G1 | Enable repeatable, controller-first scene review with minimal on-screen chrome |
| G2 | Enforce a fixed evaluation order from a configurable JSON scene list |
| G3 | Capture per-participant, per-scene ordinal scores in durable local JSON |
| G4 | Preserve the USD Viewer base app (streaming-ready, viewport-only) without forking setup/messaging extensions |

---

## 3. Non-Goals

| ID | Out of scope |
|----|--------------|
| NG1 | Web streaming client UI or remote score aggregation |
| NG2 | Folder browsing / ad-hoc scene selection (scene list is authoritative) |
| NG3 | Multi-user concurrent sessions within one app instance |
| NG4 | Automatic scene orientation or `cameras.json` placement (may be added in a future revision; not required for v1 unless scenes fail to render) |
| NG5 | Modifying `nycu.my_usd_viewer_setup_extension` or `nycu.my_usd_viewer_messaging_extension` |

---

## 4. Users & Primary Workflow

**Actor:** Evaluation participant (single user per app session).

```
Launch app
  → Enter participant name (required, blocking)
  → Read ordered scene list from JSON
  → Load scene[0] (USDZ)
  → Navigate freely (DS4 + built-in camera controls)
  → [Optional] Open scoring panel → adjust 5 sliders → Next
  → Scores saved under participant name → load scene[1]
  → … repeat until list exhausted → show completion state
```

---

## 5. Architecture

### 5.1 Application stack

```
nycu.mos_app.kit  (unchanged except one new dependency line)
│
├── [Existing — do not modify]
│   ├── nycu.my_usd_viewer_setup_extension   Viewport-only layout, menu hidden
│   └── nycu.my_usd_viewer_messaging_extension   Streaming messaging (idle in local use)
│
└── [New]
    └── nycu.mos_app_extension  (order = 1100)
          ├── participant_prompt.py   Name entry on startup
          ├── scene_catalog.py        JSON scene list loader + index state
          ├── stage_loader.py         USDZ open/close + initial camera capture
          ├── navigation_controller.py  DS4/keyboard input routing
          ├── scoring_ui.py           Toggleable scoring window + focus model
          └── score_store.py          Per-participant JSON persistence
```

### 5.2 Kit file change (minimal)

Add to `[dependencies]` in `nycu.mos_app.kit`:

```toml
"nycu.mos_app_extension" = { order = 1100 }
```

Optional app-level settings (recommended, set in `.kit` or extension defaults):

```toml
[settings.exts."nycu.mos_app_extension"]
sceneListPath = "${app}/../data/mos_scenes.json"
scoresDir = ""  # empty → platform default (see §8.2)
gamepadCameraControl = true
```

### 5.3 Extension dependencies (`extension.toml`)

```toml
[dependencies]
"omni.kit.uiapp" = {}
"omni.usd" = {}
"omni.kit.viewport.utility" = {}
"omni.kit.commands" = {}
"omni.kit.manipulator.camera" = {}  # gamepad camera (already in app)
```

---

## 6. Functional Requirements

### FR-1 Participant identification (startup)

| ID | Requirement |
|----|-------------|
| FR-1.1 | On first frame after extension startup, display a **modal blocking window** titled “Participant” before any scene loads. |
| FR-1.2 | Window contains: label, single-line name field, **Continue** button. |
| FR-1.3 | **Continue** is disabled until the trimmed name is non-empty (min length 1, max length 64). |
| FR-1.4 | Allowed characters: Unicode letters, digits, spaces, hyphen, underscore. Reject or strip other characters on submit. |
| FR-1.5 | On confirm, persist name in session memory and close the prompt. Scene loading (FR-2) begins only after confirmation. |
| FR-1.6 | Name is **not** re-prompted on scene advance; one name per app session. |
| FR-1.7 | Display current participant name in scoring panel header (read-only). |

**Keyboard:** Enter in the name field submits when valid (same as Continue).

---

### FR-2 Scene list & loading

| ID | Requirement |
|----|-------------|
| FR-2.1 | Load an ordered scene list from a JSON file at startup (after FR-1). Default path: `${app}/../data/mos_scenes.json`, overridable via `/exts/nycu.mos_app_extension/sceneListPath`. |
| FR-2.2 | JSON schema (v1): |

```json
{
  "version": 1,
  "scenes": [
    "/absolute/or/relative/path/to/scene_a.usdz",
    "/absolute/or/relative/path/to/scene_b.usdz"
  ]
}
```

| FR-2.3 | Paths may be absolute or relative to the JSON file’s directory. |
| FR-2.4 | Only `.usdz` (case-insensitive) entries are valid. Invalid entries are logged and skipped; if zero valid scenes remain, show error dialog and halt. |
| FR-2.5 | After list validation, automatically open `scenes[0]`. |
| FR-2.6 | Before each open, close/unload the current stage to release VRAM (same pattern as `usdz_folder_browser._unload_stage`). |
| FR-2.7 | Use `omni.usd.get_context().open_stage_async(url, LOAD_ALL)` (or synchronous equivalent with stage-event confirmation). |
| FR-2.8 | On successful open, capture **initial navigation state** (FR-3.2). |
| FR-2.9 | **Next** (FR-5.6) advances index by 1 and loads the next scene. On last scene, **Next** saves scores and shows completion UI (no further load). |
| FR-2.10 | Scene index and file path are shown in scoring panel footer when visible. |

---

### FR-3 Free navigation & reset

| ID | Requirement |
|----|-------------|
| FR-3.1 | With scoring panel **closed**, participant navigates the viewport using DS4 sticks and/or Kit’s built-in fly/navigation camera (enabled via `/persistent/app/omniverse/gamepadCameraControl = true`). |
| FR-3.2 | On each successful scene load, store **initial spot**: viewport camera world transform (position + orientation) immediately after load completes. |
| FR-3.3 | **Reset** (DS4 Triangle / keyboard **R**) restores the camera to the stored initial spot for the current scene. |
| FR-3.4 | Reset works only while scoring panel is closed (see FR-5.2). |
| FR-3.5 | Reset is idempotent and does not reload the USDZ file. |

---

### FR-4 Scoring panel — open/close

| ID | Requirement |
|----|-------------|
| FR-4.1 | Scoring panel is a floating `ui.Window`, hidden by default. |
| FR-4.2 | **Open:** DS4 **Cross (X)** or keyboard **Enter** opens the panel if closed. |
| FR-4.3 | **Close:** DS4 **Circle** or keyboard **Esc** closes the panel if open. |
| FR-4.4 | When panel opens: pause DS4 camera navigation input (sticks/triggers do not move camera); route input to scoring UI (FR-6). |
| FR-4.5 | When panel closes: resume camera navigation; restore viewport focus. |
| FR-4.6 | Opening the panel does not reset camera position. |

---

### FR-5 Scoring panel — content & submission

| ID | Requirement |
|----|-------------|
| FR-5.1 | Panel title: **Scene Scoring**. |
| FR-5.2 | Five ordinal metrics, each a discrete **5-step** slider (internal values 1–5): |

| # | Metric key (JSON) | UI label |
|---|-------------------|----------|
| 1 | `texture_fidelity` | Texture fidelity |
| 2 | `semantic_contextual_coherence` | Semantic and contextual coherence |
| 3 | `geometric_consistency` | Geometric consistency |
| 4 | `volumetric_cleanliness` | Volumetric cleanliness |
| 5 | `overall_quality` | Overall quality |

| FR-5.3 | Step labels (displayed adjacent to slider): **Very poor**, **Poor**, **Average**, **Good**, **Very good** — mapped to values 1–5 respectively. |
| FR-5.4 | Default slider value on new scene: **3 (Average)**, unless prior saved scores exist for this participant + scene (FR-7.3). |
| FR-5.5 | Sliders are integer-only; no fractional values. |
| FR-5.6 | **Next** button: (a) persist scores for current participant + scene (FR-7), (b) close scoring panel, (c) advance to next scene (FR-2.9). |
| FR-5.7 | **Next** on the final scene: save scores, show “All scenes complete” message; app remains open for review until user quits. |
| FR-5.8 | No separate Save button in v1; **Next** is the sole submit action. |

---

### FR-6 Controller & keyboard — scoring panel focus model

When scoring panel is **open**, DS4 and keyboard control the focused widget:

| Input | Action |
|-------|--------|
| DS4 D-pad Up / Down | Move focus between sliders and **Next** (vertical list order) |
| DS4 D-pad Left / Right | Decrease / increase value of focused slider (clamped 1–5) |
| DS4 Cross (X) / Enter | Activate focused **Next** button; on sliders, no-op or confirm (implementation choice: prefer **Next** activation only when **Next** is focused) |
| DS4 Circle / Esc | Close scoring panel (FR-4.3) |
| Keyboard Tab / Shift+Tab | Move focus (accessibility fallback) |
| Keyboard ← / → | Adjust focused slider |

**Focus order:** Slider 1 → 2 → 3 → 4 → 5 → **Next** → (wrap).

Visual: focused control receives a highlighted border or background (consistent with `omni.ui` focus styling).

---

### FR-7 Score persistence

| ID | Requirement |
|----|-------------|
| FR-7.1 | Scores are stored per participant in a JSON file on local disk. |
| FR-7.2 | Default directory: `$XDG_STATE_HOME/nycu.mos_app_extension/scores/` (fallback: `~/.local/state/nycu.mos_app_extension/scores/`). Overridable via `/exts/nycu.mos_app_extension/scoresDir`. |
| FR-7.3 | Filename: `{sanitized_participant_name}.json` (unsafe filesystem characters replaced with `_`). |
| FR-7.4 | JSON schema (v1): |

```json
{
  "version": 1,
  "participant": "Alice",
  "sessions": [
    {
      "saved_at": "2026-07-07T03:00:00+00:00",
      "scene_path": "/data/scenes/scene_a.usdz",
      "scene_index": 0,
      "scores": {
        "texture_fidelity": 4,
        "semantic_contextual_coherence": 3,
        "geometric_consistency": 4,
        "volumetric_cleanliness": 5,
        "overall_quality": 4
      }
    }
  ]
}
```

| FR-7.5 | Each **Next** submission appends a new entry to `sessions` (do not overwrite history). |
| FR-7.6 | Writes use atomic replace (`.tmp` + `os.replace`) per `metric_sliders` pattern. |
| FR-7.7 | On scene load, if entries exist for `(participant, scene_path)`, pre-fill sliders from the **most recent** matching session entry. |
| FR-7.8 | Score files are human-readable (indent=2, sort_keys=true). |

---

## 7. Input Reference (consolidated)

| Action | DS4 | Keyboard | Precondition |
|--------|-----|----------|--------------|
| Navigate viewport | Sticks, L2/R2 | WASD / mouse (Kit defaults) | Scoring panel closed |
| Reset to initial spot | Triangle | R | Scoring panel closed |
| Open scoring panel | Cross (X) | Enter | Scoring panel closed |
| Close scoring panel | Circle | Esc | Scoring panel open |
| Focus prev/next widget | D-pad Up/Down | Tab / Shift+Tab | Scoring panel open |
| Adjust slider | D-pad Left/Right | ← / → | Scoring panel open, slider focused |
| Submit & next scene | Cross (X) on **Next** focus | Enter on **Next** focus | Scoring panel open |

**Note:** DS4 button names follow PlayStation convention (Cross = X button, bottom face button).

---

## 8. Data Files

### 8.1 Scene list (project-supplied)

**Default location:** `source/data/mos_scenes.json` (resolved via `${app}/../data/mos_scenes.json`).

Example:

```json
{
  "version": 1,
  "scenes": [
    "../datasets/eval/scene_001.usdz",
    "../datasets/eval/scene_002.usdz"
  ]
}
```

### 8.2 Scores (runtime-generated)

**Per participant:** `~/.local/state/nycu.mos_app_extension/scores/alice.json`

---

## 9. UI Specification

### 9.1 Windows

| Window | Visibility | Purpose |
|--------|------------|---------|
| Viewport | Always (from setup ext) | 3D scene |
| Participant prompt | Once at startup | Name entry |
| Scene Scoring | Toggle | Metrics + Next |
| Error / Complete | As needed | Fatal list errors, end-of-study message |

### 9.2 Layout — Scene Scoring panel

```
┌─ Scene Scoring ─────────────────────────────┐
│ Participant: Alice                          │
│                                             │
│ Texture fidelity          [====●===] Good   │
│ Semantic and contextual…  [===●====] Average│
│ Geometric consistency     [====●===] Good   │
│ Volumetric cleanliness    [=====●==] Good   │
│ Overall quality           [====●===] Good   │
│                                             │
│              [ Next ]                       │
│ Scene 2/10 · scene_002.usdz                 │
└─────────────────────────────────────────────┘
```

Approximate size: 480×360 px, dockable=false, movable=true.

---

## 10. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | Startup: name prompt appears within 2 s of viewport readiness on reference hardware (RTX GPU, local SSD). |
| NFR-2 | Scene transition (unload + load typical USDZ): target < 10 s for assets ≤ 500 MB (hardware-dependent). |
| NFR-3 | Input latency (reset, panel toggle): < 100 ms perceived. |
| NFR-4 | No network calls required for core workflow. |
| NFR-5 | Extension shuts down cleanly: release input subscriptions, destroy UI windows, cancel pending async tasks. |
| NFR-6 | Log errors (missing files, load failures) via `carb.log` / `omni.log`; show user-visible status in scoring footer or dialog. |

---

## 11. Error Handling

| Condition | Behavior |
|-----------|----------|
| Scene list file missing / invalid JSON | Modal error; app does not load scenes |
| Scene path not found | Skip with warning, offer continue to next OR halt ( **Decision:** halt and show error — participant must fix list) |
| Stage open fails | Show error dialog with path; remain on current index; allow retry via relaunch |
| Score write fails | Block **Next**; show error; keep panel open |
| DS4 not connected | Keyboard-only fallback for all actions; log info once |
| Empty participant name | Continue disabled |

---

## 12. Testing & Acceptance Criteria

### 12.1 Acceptance criteria (v1)

- [ ] **AC-1** App shows name prompt before any USDZ loads; empty name cannot proceed.
- [ ] **AC-2** First scene from JSON list loads automatically after name entry.
- [ ] **AC-3** DS4 sticks move camera with scoring panel closed; Triangle / R resets to post-load pose.
- [ ] **AC-4** Cross / Enter opens scoring panel; Circle / Esc closes it.
- [ ] **AC-5** All five sliders expose exactly five labeled steps (Very poor → Very good).
- [ ] **AC-6** D-pad navigates and adjusts sliders; **Next** is reachable and activatable via controller.
- [ ] **AC-7** **Next** writes scores to `{participant}.json` and loads the next scene.
- [ ] **AC-8** After final scene, completion message shown; no crash.
- [ ] **AC-9** Existing extensions (`nycu.my_usd_viewer_setup_extension`, `nycu.my_usd_viewer_messaging_extension`) are unchanged in source.
- [ ] **AC-10** App still launches to viewport-only layout (no menu bar).

### 12.2 Suggested automated tests

Location: `nycu.mos_app_extension/tests/`

| Test | Scope |
|------|-------|
| `test_scene_catalog.py` | JSON parsing, path resolution, `.usdz` filter |
| `test_score_store.py` | Atomic write, append, reload latest |
| `test_name_validation.py` | Trim, length, character filter |
| `test_app_startup.py` | Extension loads with `nycu.mos_app` (--no-window) |

---

## 13. Implementation Plan

| Phase | Deliverable |
|-------|-------------|
| P1 | Scaffold `nycu.mos_app_extension`, wire into `.kit`, sample `mos_scenes.json` |
| P2 | Participant prompt + scene catalog + stage loader |
| P3 | Initial camera capture + reset (R / Triangle) |
| P4 | Scoring UI + score store + **Next** flow |
| P5 | DS4 input router + focus model |
| P6 | Error handling, completion state, tests |

---

## 14. Open Questions (resolved for v1)

| Question | Decision |
|----------|----------|
| Symmetric toggle for scoring panel? | **No** — X/Enter opens, Circle/Esc closes |
| Slider scale 0–5 or 1–5? | **1–5** with five named labels (matches “five steps” requirement) |
| Overwrite or append scores? | **Append** session entries for audit trail |
| Re-prompt name each scene? | **No** — once per app launch |
| Modify setup/messaging extensions? | **No** — all logic in new extension |
| Auto `cameras.json` / orientation? | **Out of scope v1** — add if evaluation assets require it |

---

## 15. Glossary

| Term | Definition |
|------|------------|
| Initial spot | Camera transform captured immediately after a scene finishes loading |
| Scene list | Ordered JSON array of USDZ paths defining evaluation sequence |
| Participant | Human evaluator identified at startup; key for score file |
| Scoring panel | Toggleable UI for ordinal metric input and scene advance |

---

## 16. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-07-07 | — | Initial PRD from stakeholder requirements |
