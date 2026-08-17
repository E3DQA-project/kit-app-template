# MOS post-render streaming checkpoints

## The important finding

The current MOS measurements show a stable swapchain image after 2.4–7.8 seconds, but the viewer reports the stage loaded only after 22.7–28.0 seconds. That remaining ~20 seconds is not an unexplained renderer wait any more.

The local `nycu.my_usd_viewer_messaging_extension` defines its completion rule in `stage_loading.py`:

```text
USD stage begins opening
  → USD says ASSETS_LOADED
  → wait while the streaming manager says isBusy=true
  → wait two more Kit updates
  → send “stage has loaded”
```

The checkpoint experiment corrected the initial hypothesis: the streaming manager became idle after only 1.9–7.2 seconds, while `ASSETS_LOADED` did not arrive until 23.1–28.0 seconds. The actual dominant interval is therefore **`USD_ASSETS_LOADING → USD_ASSETS_LOADED`**, not `STREAMING_BUSY → STREAMING_IDLE`. Read the [asset-loading checkpoint record](../records/2026-08-17-mos-asset-loading-checkpoints.md) for the numbers.

## Exact checkpoints to add

Record each event once per MOS scene generation. The first six split the currently hidden 20-second interval; the rest explain why it was slow.

| Checkpoint | Source | Meaning | What it separates |
|---|---|---|---|
| `USD_OPENING` | `StageEventType.OPENING` | Kit has begun opening the target stage. | Old-stage teardown versus new-stage work. |
| `USD_ASSETS_LOADING` | `StageEventType.ASSETS_LOADING` | Texture/material asset loading is under way. | USD composition versus declared asset loading. |
| `USD_ASSETS_LOADED` | `StageEventType.ASSETS_LOADED` | Kit reports textures/materials loaded. | Asset loading versus post-asset streaming. |
| `STREAMING_BUSY` | `omni.streamingstatus:streaming_status`, `isBusy=true` | At least one stage streaming system is still working. | Beginning of the actual streaming gate. |
| `STREAMING_IDLE` | same event, `isBusy=false` | All stage streaming systems report idle. | End of the gate the viewer waits for. |
| `POST_STREAMING_UPDATE_1/2` | Kit update loop | The viewer deliberately waits two updates after idle. | Fixed completion-policy delay; normally tiny. |
| `VIEWER_STAGE_LOADED` | viewer `openedStageResult` dispatch | The viewer’s final completion notification. | Messaging delay after its completion conditions. |
| `STAGE_LOADING_STATUS` | `get_stage_loading_status()` | `(message, files_loaded, files_total)` snapshot when values change. | Which USD file/dependency loading work remains. |
| `GEOSTREAMING_STARTED/STOPPED` | `StageEventType.HYDRA_GEOSTREAMING_*` | Hydra geometry-streaming lifecycle, if emitted. | Geometry/3DGS-style streaming versus other streaming. |
| `GEOSTREAMING_STOPPED_NOT_ENOUGH_MEM` / `_AT_LIMIT` | same stage events | Geometry streaming stopped due to a memory or configured limit. | A capacity problem rather than ordinary completion. |
| `STREAMING_PROGRESS` / `STREAMING_ACTIVITY` | status-bar events already forwarded by the viewer extension | Progress value and human-readable activity text. | The subsystem and phase doing the work. |
| `RTX_VIEW_ASSIGNED` | existing RTX log correlation | Viewport gets a GPU assignment. | Early GPU bring-up; not final readiness. |

`get_stage_streaming_status()` is useful as a polling cross-check because it reports whether any stage streaming system is busy. The event is better for exact edge timestamps; the poll catches missed events and can include the current state in every diagnostic record.

## What the current code proves

The viewer loading manager subscribes to only three signals relevant to final completion:

1. `OPENING` records that a persisted stage is being opened.
2. `ASSETS_LOADED` starts its final-status coroutine.
3. `omni.streamingstatus:streaming_status` updates an `isBusy` flag.

Its coroutine waits until both `ASSETS_LOADED` has happened and `isBusy` is false, then waits exactly two Kit updates and sends `openedStageResult` (“stage has loaded”).

That means `VIEWER_STAGE_LOADED - STREAMING_IDLE` should be only a few frames. If it is large, we should investigate scheduling or the viewer extension itself. The measured run instead showed a short `STREAMING_BUSY → STREAMING_IDLE` interval and a long `USD_ASSETS_LOADING → USD_ASSETS_LOADED` interval. The latter contains the real cost.

## Optimization map

| Slow interval | Likely ownership | First evidence to collect | Optimization directions |
|---|---|---|---|
| `USD_OPENING → USD_ASSETS_LOADING` | USD composition / file access | loading-status message and file counts | Local SSD versus NAS comparison; simplify USD composition; remove unnecessary references; avoid archive indirection where practical. |
| `USD_ASSETS_LOADING → USD_ASSETS_LOADED` | USD asset resolution, textures, materials | changed loading-status snapshots; progress/activity text | Reduce texture/material count and size; make asset paths local/cacheable; package and reference assets efficiently. |
| `STREAMING_BUSY → STREAMING_IDLE` | Hydra/RTX streaming, GPU uploads, geometry/3DGS resources | busy/idle edges, geostreaming edges, GPU memory and queue trace | Preload/prefetch the next scene; keep reusable GPU resources warm; use LOD/proxies; reduce 3DGS point count, texture resolution, and geometry; move source data from NAS to SSD; profile GPU copies, VRAM residency, and shader/pipeline work. |
| `GEOSTREAMING_* → NOT_ENOUGH_MEM/AT_LIMIT` | GPU memory pressure or streaming budget | explicit stop reason; VRAM telemetry | Reduce working set; increase an intentionally chosen streaming budget only after measuring headroom; eliminate duplicate resident data; use lower-detail assets. |
| `STREAMING_IDLE → VIEWER_STAGE_LOADED` | Viewer completion policy | two update timestamps and dispatch timestamp | Usually do not optimize first: the implementation deliberately waits only two frames. Validate before changing. |
| `VIEWER_STAGE_LOADED → FIRST_USER_ACTION` | Human reaction / input routing | first input marker | Do not call it load time. It is a useful validation upper bound only. |

## Next experiment

The lifecycle timestamps are now implemented and measured. Keep loading behavior unchanged, but run the same sequence from NAS and local SSD while tracing **`USD_ASSETS_LOADING → USD_ASSETS_LOADED`** with Kit/Tracy CPU+GPU profiling. The current loading-status API produced only a final empty snapshot, so it cannot identify the late asset by itself.

The trace should distinguish asset I/O / USDZ archive work, USD and MDL/material processing, texture work, GPU upload, shader/pipeline work, or another asynchronous dependency.

## Source locations

- Viewer completion policy: `source/extensions/nycu.my_usd_viewer_messaging_extension/nycu/my_usd_viewer_messaging_extension/stage_loading.py`
- Stage-loading and streaming APIs: installed `omni.usd` Kit 110 Python definitions (`get_stage_loading_status`, `get_stage_streaming_status`, and `StageEventType`).
- Measurements: [MOS capture and user-action run](../records/2026-08-17-mos-capture-and-user-action-run.md).
