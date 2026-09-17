# MOS scene-loading gap investigation — 2026-08-20

This investigation was run in the isolated worktree `investigate/mos-scene-gap`, based on cleanup commit `ff57572`. The production cleanup worktree was not modified.

## What was measured

Scene fixture:

`/mnt/gen5_SSD/pierce/kit-app-template/_mos_asset_loading_experiment/ssd_trace_one_scene.json`

Runtime log:

`/home/pierce/.nvidia-omniverse/logs/Kit/MOS App/0.1/kit_20260820_201451.log`

Activity profile:

`/home/pierce/.cache/ov/Kit/110.2/698af100/activities/generated_3dgs_opt.activity`

GPU samples captured in the diagnostic worktree:

`_mos_asset_loading_experiment/mos_gap_activity_gpu.csv`

The run used the optional settings `sceneLoadingActivityCapture=true` and `sceneLoadingNvtxCapture=true`.

## Timeline

Times below are relative to the app's scene `BEGIN` marker.

| Checkpoint | Time | Meaning |
| --- | ---: | --- |
| `BEGIN` | 0 ms | MOS starts loading the scene. |
| `STAGE_OPENED` | 140 ms | USD stage object is open. |
| `CAMERA_READY` / `NAV_READY` | 143–144 ms | Camera and navigation metadata are ready. |
| `FIRST_POST_LOAD_UPDATE` | 147 ms | First Kit update after stage setup. |
| `RENDER_STABLE` | 7,719 ms | Three captured viewport samples are unchanged. |
| `USD_ASSETS_LOADING` | 7,053 ms after stream open | Kit begins the long asset/streaming phase. |
| `ACTIVITY_SCENE_LOADING_CAPTURE_STARTED` | same instant | Activity capture starts. |
| `NVTX_SCENE_LOADING_RANGE_STARTED` | same instant | NVTX range starts. |
| `USD_ASSETS_LOADED` | 27,445 ms after stream open | Kit reports the asset phase complete. |
| `STREAMING_GATE_CLEAR` | 27,448 ms after stream open | MOS removes the streaming gate. |
| `VIEWER_STAGE_LOADED` | 27,463 ms after stream open | Viewer-facing loaded signal. |
| `FIRST_USER_ACTION` | 29,275 ms after `BEGIN` | First keyboard input was received. |

The direct `USD_ASSETS_LOADING → USD_ASSETS_LOADED` interval was approximately **20.392 seconds**. This is the user-visible gap being investigated.

## What the profiler did and did not show

The activity file contained only short named spans in the captured interval. The largest named span was approximately:

- `Post Sync`: 69 ms
- `USD Context`: 1.14 ms
- `SceneDelegate`: 1.06 ms
- `Hydra`: 0.89 ms
- shader compile/variation spans: each roughly 0.9–1.0 ms

This means the activity profiler is not exposing the owner of most of the 20-second wait. It does not prove that the work is absent; it proves that this activity capture is too coarse or that the wait occurs below the activity instrumentation boundary.

## GPU evidence

During the exact gap, 84 samples showed approximately:

- GPU utilization: mean 5.2%, maximum 17%
- VRAM: mean 5.0 GB, maximum 7.5 GB
- board power: mean 70.7 W, maximum 77.5 W

The GPU was not saturated. This is consistent with a CPU-side wait, a driver synchronization wait, or work submitted in a way that ordinary utilization sampling does not expose.

## Current conclusion

The bottleneck is not stage opening, camera setup, first presentation, or ordinary GPU throughput. The strongest current hypothesis remains a CPU/driver synchronization path associated with RTX/Hydra/streaming completion. The next useful instrument is a thread-level stack sample during the exact gap, correlated with the NVTX range and GPU telemetry. The activity profile alone cannot identify the blocking function.

## Reproduction helper

`tools/mos_gap_capture.sh OUTPUT_DIR SCENE_LIST_JSON` launches the isolated MOS app with activity/NVTX capture enabled and records GPU telemetry beside the Kit stdout log.
