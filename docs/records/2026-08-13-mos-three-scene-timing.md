# MOS Three-Scene Loading Timing Record — 2026-08-13

## Run context

- Application: `nycu.mos_app.kit`
- Session: `mos_app` tmux session
- Build: lifecycle timestamp instrumentation added on branch `cleanup`
- Scene list: 7 NAS-backed USDZ scenes
- Completion marker: `READY_FOR_INTERACTION`, emitted on the first guarded Kit update after scene, camera, and navigation setup.

`READY_FOR_INTERACTION` is a practical application-side readiness marker. It is not an exact GPU-completion or display-scanout measurement.

## Results

| Scene | USDZ file | Stage open | Orientation | Camera | Navigation | First update/render proxy | Total to interaction |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `generated_3dgs_opt.usdz` | 173 ms | 0 ms | 5 ms | 0 ms | 5 ms | **183 ms** |
| 2 | `generated_3dgs_opt_downsample_p0.25.usdz` | 213 ms | 0 ms | 3 ms | 1 ms | 11 ms | **228 ms** |
| 3 | `generated_3dgs_opt_downsample_p0.50.usdz` | 228 ms | 0 ms | 4 ms | 0 ms | 11 ms | **243 ms** |

## Raw lifecycle timestamps

### Scene 1 — generation 1

```text
BEGIN                  0 ms
STAGE_OPENED         173 ms
ORIENTATION_DONE     173 ms
CAMERA_READY         178 ms
NAV_READY            178 ms
FIRST_RENDER_FRAME   183 ms
READY_FOR_INTERACTION 183 ms
```

### Scene 2 — generation 2

```text
BEGIN                  0 ms
STAGE_OPENED         213 ms
ORIENTATION_DONE     213 ms
CAMERA_READY         216 ms
NAV_READY            217 ms
FIRST_RENDER_FRAME   228 ms
READY_FOR_INTERACTION 228 ms
```

### Scene 3 — generation 3

```text
BEGIN                  0 ms
STAGE_OPENED         228 ms
ORIENTATION_DONE     228 ms
CAMERA_READY         232 ms
NAV_READY            232 ms
FIRST_RENDER_FRAME   243 ms
READY_FOR_INTERACTION 243 ms
```

## Interpretation

The dominant measured interval is `BEGIN → STAGE_OPENED`: 173–228 ms, or approximately 94% of each measured transition.

Orientation, camera setup, navigation setup, and the first Kit update collectively account for 10 ms, 15 ms, and 15 ms respectively. They are not the primary source of the current measured overhead.

The next investigation should focus on what happens inside the stage-open interval: closing the prior stage, NAS file access, USDZ reading/decompression, USD stage population, and any deferred Kit work that occurs before the `OPENED` event. Do not optimize camera or UI code first.

## Evidence and limitations

- Source: `/home/pierce/.nvidia-omniverse/logs/Kit/MOS App/0.1/kit_20260814_011259.log`
- All three scenes reported `ORIENTATION_DONE ok=True` and `CAMERA_READY source=cameras.json`.
- No stale callbacks appeared: each lifecycle sequence used a unique generation and emitted one readiness pair.
- This run contains three sequential transitions after one application launch. It does not separately measure a cold first-ever shader/cache run, GPU completion, or display scanout.
