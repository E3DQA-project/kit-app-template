# MOS Headless Run Findings

**Date:** 2026-07-28  
**Target:** `source/apps/nycu.mos_app.kit`  
**Purpose:** Determine whether the MOS scene-transition benchmark can run without the GUI workstation workflow.

## Run Performed

The built Kit executable was launched headlessly for up to 90 seconds:

```bash
timeout 90s _build/linux-x86_64/release/kit/kit \
  source/apps/nycu.mos_app.kit --allow-root --portable \
  --portable-root _build/linux-x86_64/release --no-window \
  --ext-folder source/extensions --ext-folder source/apps \
  --/app/extensions/registryEnabled=0 \
  --/app/extensions/generateVersionLock=0
```

The configured USDZ asset is present and readable: `1,247,987,111` bytes. The run created [`kit_20260728_224027.log`](../_build/linux-x86_64/release/logs/Kit/MOS%20App/0.1/kit_20260728_224027.log).

## Result

The application exited during dependency resolution, before any MOS extension code or scene loading ran:

```text
Failed to resolve extension dependencies
No versions of omni.anim.curve.core satisfying version =1.6.0
Exiting app because of dependency solver failure
```

Consequently, this run produced **no valid scene-transition, preload, GPU, or GUI timing data**. It does establish that the current local build cache is not self-contained for this headless launch. The app’s version-locked configuration requests `omni.anim.curve.core-1.6.0`, but that package is absent from `_build/linux-x86_64/release/extscache`.

## Interpretation

The headless approach remains viable, but the environment must first be rebuilt or its dependencies restored. Separately, the current MOS extension requires the participant prompt before `_start_evaluation()` and `_load_scene()` execute, so a useful automated benchmark will need a diagnostic/non-interactive mode after dependency setup.

## Planned benchmark result

After removing the stale `nycu.mos_app_retry.kit` entry from `repo.toml`, rebuilding, and enabling the non-interactive benchmark mode, the wrapper completed all seven scenes headlessly. The first cold dual-slot load took **41.863 s**. Once disk preload and GPU standby were overlapped, the remaining six scene transitions took **0.004–0.008 s** each. Disk preload remained the background cost at approximately **2.8–13.4 s**, while GPU standby composition was sub-second after the first warm-up.

The detailed measurements are in [`mos_scene_benchmark.md`](mos_scene_benchmark.md) and [`mos_scene_benchmark.json`](mos_scene_benchmark.json). This confirms the 20–25 second subjective transition overhead is avoidable for subsequent scenes: scene preparation must happen before the participant transition, and the visible transition should activate a parked GPU-resident slot.
