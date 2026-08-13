# MOS Scene-Loading Overhead Investigation

## Objective

Measure one MOS USDZ scene transition from the participant selecting **Next** through the strongest practical evidence that the requested scene is rendered and usable. Produce terminal-visible records with one elapsed-time origin, capture those records from the `mos_app` tmux session, and use the resulting timing gaps to choose the next optimization experiment.

## Existing material assessment

`docs/superpowers/plans/2026-07-29-mos-scene-readiness-logging.md` remains relevant as the initial instrumentation design. Its event sequence and no-behavior-change constraint are sound.

It is not yet an executable measurement plan because:

- Its checkboxes do not reflect current state: `load_diagnostics.py` and its formatter test already exist, but the MOS extension does not import or emit those records.
- It has no protocol for observing the interactive `mos_app` tmux session or retaining per-transition evidence.
- It does not distinguish stage-open completion from renderer/display readiness.
- It must be updated for the current scene list and runtime paths before timing data are compared.

This document supersedes it for the measurement workflow; the older file remains useful as historical design context.

## Timing contract

Each scene transition receives a monotonically increasing load generation and an `_LoadDiagnostics` instance. Every record begins with `[MOS_LOAD]` and includes `generation`, `scene`, `file`, `event`, and `elapsed_ms`, where `elapsed_ms=0` is immediately before the existing unload/open sequence.

| Event | Measured boundary | Interpretation |
|---|---|---|
| `BEGIN` | Immediately before `_unload_stage()` / `open_stage()` | Start of application-controlled transition. |
| `STAGE_OPENED` | Matching `StageEventType.OPENED` and requested URL verification | Requested USDZ has become the active Kit stage; not a render-complete claim. |
| `ORIENTATION_DONE` | Orientation and up-axis work completes | Small post-stage setup interval; include `ok=true/false`. |
| `CAMERA_READY` | `cameras.json` pose applied and viewport camera activated | Camera setup succeeded. |
| `CAMERA_FALLBACK` | No camera metadata or setup failure | Scene continues with a documented fallback. |
| `NAV_READY` | Navigation settings applied and state becomes `NAVIGATING` | Input/UI state is ready. |
| `FIRST_RENDER_FRAME` | First guarded Kit update after post-load setup | Best available in-app proxy that rendering can begin; not display scanout. |
| `READY_FOR_INTERACTION` | Same guarded update after `FIRST_RENDER_FRAME` | Practical readiness marker, explicitly weaker than “all pixels displayed.” |

For each adjacent pair, the report will calculate the delta. Any unobservable interval—such as GPU completion after the update callback or display scanout—will be labeled unknown rather than inferred.

## Implementation plan

1. **Make diagnostics live.** Import the existing formatter into `nycu.mos_app_extension`. On every `_load_scene`, cancel old stage/render subscriptions, increment the generation, initialize timing, then emit `BEGIN`. Emit failure records for subscription/open failures.
2. **Instrument post-load work.** Emit `STAGE_OPENED` only after the current URL matches the requested scene. Emit orientation and camera outcomes from `_post_load`; capture camera resolution/activation failures without changing fallback behavior. Emit `NAV_READY` immediately after the app restores navigating state.
3. **Add a generation-guarded render proxy.** Subscribe once to the Kit update stream after post-load setup. The callback must verify the active generation and scene before emitting `FIRST_RENDER_FRAME` then `READY_FOR_INTERACTION`, dispose itself, and be cleared on shutdown, open failure, or the next load. It must never claim GPU completion or display scanout.
4. **Test the ownership rules.** Keep the formatter’s pure unit tests. Add narrow tests for generation mismatch, exactly-once readiness output, and stale subscription cleanup. Run Python compilation and the focused MOS test suite.
5. **Observe interactive runs.** Always activate `pierce_base` before invoking tmux. Capture the pane before and after each participant-triggered transition:

   ```bash
   conda activate pierce_base
   tmux capture-pane -pt mos_app -S -400
   ```

   Record only new `[MOS_LOAD]` records, scene index/path, and user-observed readiness. Capture at least one cold initial load and three sequential Next-driven transitions. Do not introduce preloading or renderer configuration changes while establishing this baseline.
6. **Report and optimize iteratively.** Write a timing table with total time and per-stage deltas. Compare cold versus steady state and note the scene source (NAS/SSD) plus file variant. Select exactly one next experiment based on the largest repeatable interval; preserve the baseline before changing preload, caching, renderer, or stage-lifetime behavior.

## Acceptance criteria

- One transition emits a complete ordered lifecycle sequence with a shared generation and elapsed-time origin.
- A new transition cannot receive a stale readiness record from an earlier scene.
- The tmux-derived evidence includes at least four transitions: one cold and three steady-state.
- The resulting report explains which intervals are measured, which are practical proxies, and which remain unknown.
- No scene-loading or scoring behavior changes beyond diagnostic instrumentation.

## Known baseline and constraints

- A historical `mos_app` pane captured on 2026-07-29 showed `Loading` to ready status in approximately 121–233 ms across four SSD-backed scene transitions. Those records omit stage-event, camera, and render boundaries, so they are not comparable to the planned full lifecycle table.
- The current source tree includes the formatter helper but has not integrated it into the extension lifecycle.
- The `mos_app` session must be accessed through the `pierce_base` Conda environment; `tmux` is not available on the base shell PATH.
