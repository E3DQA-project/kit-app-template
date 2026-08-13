# MOS Scene Readiness Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add terminal-visible lifecycle diagnostics that identify when each MOS USDZ scene becomes ready for participant interaction.

**Architecture:** Add a small dependency-free diagnostic helper to the MOS extension that records a monotonic scene start time and emits consistently formatted `[MOS_LOAD]` records. Hook it into the existing `_load_scene`, `_on_stage_event`, `_post_load`, navigation setup, and one deferred Kit update callback; no scene-loading behavior or application wiring changes.

**Tech Stack:** Python, `time.perf_counter`, `omni.log`, Kit update event stream, unittest.

## Global Constraints

- Preserve ordered scene loading, participant-scoped score persistence, and the `${app}/../data/mos_scenes.json` override.
- Do not edit generated artifacts, cached extensions, legacy apps, or score data.
- Do not claim GPU completion beyond the strongest signal available from the Kit update/render callback.

---

### Task 1: Add and test the pure load-diagnostic formatter

**Files:**
- Create: `source/extensions/nycu.mos_app_extension/nycu/mos_app_extension/tests/test_load_diagnostics.py`
- Modify: `source/extensions/nycu.mos_app_extension/nycu/mos_app_extension/extension.py`

**Interfaces:**
- Produces `_LoadDiagnostics(scene_index, scene_total, scene_path, clock=None)` with `begin()`, `elapsed_ms()`, and `record(event, **fields)` methods.
- `record()` emits one `omni.log.info` line beginning `[MOS_LOAD]` and containing stable `event=`, `scene=`, `file=`, and `elapsed_ms=` fields.

- [ ] **Step 1: Write the failing tests** for stable event formatting and monotonic elapsed time using an injected clock and a patched logger.
- [ ] **Step 2: Run the focused test and verify it fails** because `_LoadDiagnostics` does not exist.
- [ ] **Step 3: Implement the minimal helper** using `time.perf_counter` by default and basename-only file output to keep terminal lines readable.
- [ ] **Step 4: Run the focused test and verify it passes.**

### Task 2: Instrument the MOS scene lifecycle

**Files:**
- Modify: `source/extensions/nycu.mos_app_extension/nycu/mos_app_extension/extension.py`

**Interfaces:**
- The extension owns the active `_load_diag` and `_render_sub` handles.
- `_schedule_ready_check()` subscribes once to the Kit update stream and records `FIRST_RENDER_FRAME` then `READY_FOR_INTERACTION` for the current scene.

- [ ] **Step 1: Add failing tests** for readiness-check generation guards and cleanup behavior using lightweight fake subscriptions/diagnostics.
- [ ] **Step 2: Run the focused tests and verify the expected failures.**
- [ ] **Step 3: Add lifecycle fields and records:** `BEGIN` before `open_stage`, `STAGE_OPENED`, `ORIENTATION_DONE`, `CAMERA_READY`/`CAMERA_FALLBACK`, `NAV_READY`, and the deferred render/readiness pair.
- [ ] **Step 4: Cancel stale subscriptions and clear diagnostic state** on shutdown, failed stage open, and a new scene load.
- [ ] **Step 5: Run all focused tests and verify they pass.**

### Task 3: Static and runtime verification

**Files:**
- No additional production files.

- [ ] **Step 1: Run Python syntax compilation for the MOS extension and tests.**
- [ ] **Step 2: Run the focused unittest module.**
- [ ] **Step 3: Activate `pierce_base`, capture the existing `mos_app` tmux pane, and launch or observe the MOS app as appropriate.**
- [ ] **Step 4: Confirm the terminal contains the lifecycle sequence and report any Kit/GPU signal limitations explicitly.**
