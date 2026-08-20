# MOS scene-loading consolidated evidence record

## Scope

This record consolidates the current scene-loading knowledge through the final 2026-08-17 one-scene run. It combines source inspection, MOS lifecycle logs, Kit activity data, storage A/B testing, CPU tracing, Vulkan/CUDA tracing, driver telemetry, and configuration A/B testing.

The central question is: why does a scene that opens in milliseconds take roughly 20–30 seconds before the participant can use it?

## Latest clean run

- Application: `nycu.mos_app.kit`
- Kit: `110.2.0+feature.342835.698af100.gl`
- Renderer: RTX
- GPU mode: `renderer.multiGpu.enabled = false`
- Scene: `generated_3dgs_opt.usdz`
- Source: local SSD mirror
- Kit log: `/home/pierce/.nvidia-omniverse/logs/Kit/MOS App/0.1/kit_20260817_232351.log`
- Activity trace: `/home/pierce/.cache/ov/Kit/110.2/698af100/activities/generated_3dgs_opt.activity`

## Latest lifecycle numbers

All `MOS_LOAD` elapsed values below are measured from scene `BEGIN`.

| Checkpoint | Elapsed | Evidence |
|---|---:|---|
| `BEGIN` | 0 ms | MOS diagnostics |
| `omni.usd` opened successfully | ~99 ms | Kit log |
| `STAGE_OPENED` | 129 ms | MOS diagnostics |
| `ORIENTATION_DONE` | 129 ms | MOS diagnostics |
| `CAMERA_READY` | 131 ms | MOS diagnostics |
| `NAV_READY` | 132 ms | MOS diagnostics |
| `FIRST_PRESENT_TO_VIEWPORT` | 132 ms | renderer event |
| `POST_PRESENT_FRAME_BUFFER` | 133 ms | renderer event |
| `FIRST_POST_LOAD_UPDATE` | 134 ms | Kit update |
| `VIEWPORT_BASELINE_CAPTURED` | 183 ms | swapchain capture |
| `USD_ASSETS_LOADING` | 7.087 s | streaming status |
| `RENDER_STABLE` | 7.726 s | three stable viewport samples |
| `USD_ASSETS_LOADED` | 27.336 s | streaming/activity status |
| `STREAMING_GATE_CLEAR` | 27.339 s | viewer extension |
| `VIEWER_STAGE_LOADED` | 27.353 s | viewer extension |
| `FIRST_USER_ACTION` | 27.829 s | `W` keyboard input |

Derived intervals:

- `BEGIN → STAGE_OPENED`: **0.129 s**
- `STAGE_OPENED → FIRST_PRESENT_TO_VIEWPORT`: **0.003 s**
- `BEGIN → RENDER_STABLE`: **7.726 s**
- `RENDER_STABLE → USD_ASSETS_LOADED`: **19.610 s**
- `USD_ASSETS_LOADING → USD_ASSETS_LOADED`: **20.249 s** in this run
- `USD_ASSETS_LOADED → VIEWER_STAGE_LOADED`: **17 ms**
- `VIEWER_STAGE_LOADED → FIRST_USER_ACTION`: **476 ms**
- `BEGIN → FIRST_USER_ACTION`: **27.829 s**

The asset-loading interval begins before `RENDER_STABLE`, so the two intervals overlap. They must not be added together.

## Detailed events inside the latest slow window

| Log time from scene `BEGIN` | Event or activity | Duration/meaning |
|---:|---|---|
| +7.087 s | `STREAMING_IDLE` and `USD_ASSETS_LOADING` | Kit announces the late asset phase. |
| +7.090 s | `MdlStates.mdl` activity | Progress `1.0`; short activity span. |
| +7.090 s | `UsdPreviewSurfaceMonolithic.mdl` activity | Progress `1.0`; short activity span. |
| +7.091 s | `UsdPreviewSurfaceMonolithicLite.mdl` activity | Progress `1.0`; short activity span. |
| +7.304–7.726 s | viewport capture samples | Three samples used for stability. |
| +7.726 s | `RENDER_STABLE` | Image no longer changes under the stability test. |
| +7.726–27.336 s | no named lifecycle activity | **20.610 s with no finer-grained checkpoint.** |
| +27.336 s | `USD_ASSETS_LOADED` | Kit releases its asset-completion signal. |
| +27.339 s | `STREAMING_GATE_CLEAR` | Viewer gate clears. |
| +27.353 s | `VIEWER_STAGE_LOADED` | Viewer notifies completion. |
| +27.829 s | first `W` | MOS receives deliberate input. |

## Kit activity-trace breakdown

The generated activity file contains these named spans:

| Activity span | Observed duration |
|---|---:|
| `Stage / Opened / USD Context` | ~25 ms per recorded pass |
| `SceneDelegate` | ~17–18 ms per recorded pass |
| `Hydra` | ~2 ms per recorded pass |
| `Populate Fabric` | ~1–2 ms per recorded pass |
| `MdlStates.mdl` compile | ~1 ms |
| MDL shader variations | ~8–10 ms per recorded span |
| `UsdPreviewSurfaceMonolithic.mdl` compile | ~4 ms |
| `UsdPreviewSurfaceMonolithicLite.mdl` compile | ~1–3 ms |
| `Render Thread / Post Sync` | **6.984 s** |

The activity trace has a large unlabelled period after the recorded render-thread synchronization and before its activity end. It does not expose a named “texture upload,” “GPU wait,” or “USDZ decompression” span for the missing 20 seconds.

## Historical lifecycle runs

The early 2026-08-13 record measured only stage-open and app-side setup, producing totals around 183–243 ms. Those numbers were valid for the boundaries they measured but were not participant-visible readiness measurements.

Later runs established the broader range:

| Run | Stable render | Assets loaded | Viewer completion | First input |
|---|---:|---:|---:|---:|
| 2026-08-17 checkpoint run, scene 1 | 0.131 s | 27.989 s | 28.007 s | 28.453 s |
| 2026-08-17 checkpoint run, scene 2 | 0.233 s | 23.053 s | 23.071 s | 23.550 s |
| 2026-08-17 checkpoint run, scene 3 | 0.213 s | 24.509 s | 24.527 s | 24.879 s |
| 2026-08-17 checkpoint run, scene 4 | 0.230 s | 26.423 s | 26.441 s | 26.929 s |

A profiled run can be slower than an unprofiled run and must not be used as a baseline benchmark.

## Storage A/B

Matched NAS and SSD scene closures were tested, including camera metadata after an initial incomplete SSD mirror was excluded.

| Scene | NAS duration | SSD duration |
|---|---:|---:|
| full | 20.731 s | 20.852 s |
| p0.25 | 20.631 s | 21.036 s |
| p0.50 | 20.599 s | 24.280 s |
| p0.75 | 20.800 s | 20.750 s |
| Median | **20.681 s** | **20.944 s** |

Conclusion: storage location did not consistently control the delay. The p0.50 SSD outlier shows that local conditions can matter, but the repeated near-20-second behavior is not explained by SSD bandwidth alone.

## Trace evidence

### CPU activity trace

The CPU trace captured an approximately 20.7-second nested operation during the asset-loading interval:

```text
RtxHydraEngine::endFrame
  Render graph command list submission
    CUDA submit       carb.graphicsmux/Submission.cpp
      CUDA command    carb.graphicsmux/Submission.cpp
        CommandList::waitForLastSubmission
                         carb.graphicsmux/CommandList.cpp
```

This is CPU-side evidence that the render thread is blocked in RTX graphicsmux submission completion. It does not prove that a CUDA kernel is running for 20 seconds.

### Vulkan trace

The valid one-scene Vulkan report showed only about 2–5 ms of Vulkan work per second in the approximately 20-second window. The largest Vulkan burst was about 17.7 ms. Vulkan alone does not explain the wall-clock delay.

### CUDA plus Vulkan trace

The CUDA-plus-Vulkan report contained no long CUDA kernel or CUDA memory-copy operation. It showed short Vulkan/CUDA external-memory interoperability calls. This rules out a normal CUDA runtime kernel or memcpy as the directly observed 20-second event, but does not see inside Kit's lower-level graphics backend synchronization.

### Driver telemetry

During a 19.749-second asset-loading interval:

| Metric | Observation |
|---|---:|
| GPU utilization | 5% mean, 19% maximum |
| VRAM | 4.45–5.56 GB of 32 GB |
| Board power | 51.6–79 W |
| GPU-saturated samples | 0 of 197 |

This is negative evidence against ordinary GPU saturation and VRAM exhaustion.

## Configuration experiments

### Single-GPU A/B

The machine exposes one relevant NVIDIA GPU, but MOS originally had multi-GPU mode enabled. Disabling it produced:

- Multi-GPU configuration: **20.852 s**
- Single-GPU configuration: **19.591 s**
- Improvement: **1.261 s / 6.0%**

Keep single-GPU mode enabled, but it is not the main solution.

### Kit upgrade and startup PSO hang

Kit was upgraded from 110.0.0 to 110.2.0. On a cold shader cache, Kit then repeatedly logged `Waiting for RtPso async group async compilation`; the participant prompt was not interactive and the launcher eventually killed the process.

MOS was given asynchronous shader-finalization settings. After rebuilding:

- `app ready`: about **2.982 s**
- participant prompt: about **3.014 s**
- no repeated PSO wait in the startup log

This fixed the startup usability problem, but the later scene-loading interval remained about 20 seconds. It is a separate problem.

## Current conclusion

The high-confidence facts are:

1. USDZ opening and MOS setup are fast.
2. A stable image appears well before the viewer declares the stage loaded.
3. The participant-visible delay is dominated by the interval ending at `USD_ASSETS_LOADED`.
4. NAS versus SSD does not remove it.
5. MDL/material activity recorded by Kit is short.
6. CPU tracing shows a long RTX graphicsmux submission wait.
7. Vulkan/CUDA traces and driver telemetry do not expose a corresponding long ordinary GPU workload.
8. The exact blocked backend operation remains unknown.

The next investigation must target the graphics backend/driver boundary, not more Python-level parallelism experiments.
