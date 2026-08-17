# MOS NAS/SSD baseline and CPU trace — 2026-08-17

## Goal

Determine whether the measured `USD_ASSETS_LOADING → USD_ASSETS_LOADED` delay is primarily NAS I/O, then capture the responsible work without changing the baseline measurement.

## Controlled inputs

- Four USDZs from `photorealistic/index_0003`.
- NAS source and local-SSD mirror had matching SHA-256 values for all four USDZs.
- The local mirror also preserved the sibling `geom_optim/output/cameras.json`; all four accepted SSD scenes emitted `CAMERA_READY`.
- NAS log: `/home/pierce/.nvidia-omniverse/logs/Kit/MOS App/0.1/kit_20260817_201515.log`
- Accepted SSD log: `/home/pierce/.nvidia-omniverse/logs/Kit/MOS App/0.1/kit_20260817_202246.log`
- A prior SSD attempt (`kit_20260817_201844.log`) is excluded: it lacked `cameras.json` and emitted `CAMERA_FALLBACK` for every scene.

## Storage A/B result

All values are milliseconds from MOS `BEGIN`. The primary metric is the difference between `USD_ASSETS_LOADED` and `USD_ASSETS_LOADING`.

| Scene | NAS asset start | NAS asset loaded | NAS duration | SSD asset start | SSD asset loaded | SSD duration | SSD − NAS |
|---|---:|---:|---:|---:|---:|---:|---:|
| `generated_3dgs_opt.usdz` | 7,226 | 27,957 | 20,731 | 7,223 | 28,075 | 20,852 | +121 |
| `...downsample_p0.25.usdz` | 1,929 | 22,560 | 20,631 | 1,962 | 22,998 | 21,036 | +405 |
| `...downsample_p0.50.usdz` | 3,634 | 24,233 | 20,599 | 221 | 24,501 | 24,280 | +3,681 |
| `...downsample_p0.75.usdz` | 5,354 | 26,154 | 20,800 | 5,386 | 26,136 | 20,750 | −50 |
| **Median** | — | — | **20,681** | — | — | **20,944** | **+263** |

The SSD run was not faster. Three of four scenes were within 0.4 seconds of NAS; the p0.50 SSD run was slower. This single app-cold replica does not quantify run-to-run variance, but it clearly rules out “copy the USDZs to SSD” as the first optimization.

## Trace experiment

- Scene: local-SSD `generated_3dgs_opt.usdz`.
- CPU trace: `_mos_asset_loading_experiment/mos-ssd-scene-loading-cpu-trace.gz` (66 MB compressed; gzip validation passed).
- Trace hook markers:

```text
ACTIVITY_SCENE_LOADING_CAPTURE_STARTED  7,103 ms after BEGIN
ACTIVITY_SCENE_LOADING_CAPTURE_STOPPED 27,957 ms after BEGIN
Captured interval                         20,854 ms
```

The hook therefore covers the intended USD asset-loading period exactly.

### CPU-trace evidence inside the 20.854-second capture

The longest complete spans are in the RTX/CUDA render submission and fence-wait path:

| Span | Approximate summed span time | Interpretation |
|---|---:|---|
| `CUDA command` / `CUDA submit` | ~20.73 s | CPU submits or waits through the GPU/CUDA path during nearly the entire interval. |
| `RtxHydraEngine::endFrame` / `RG EndFrame` | ~20.70 s | RTX Hydra’s end-of-frame path is blocked for nearly the same interval. |
| `CommandList::waitForLastSubmission` | ~20.70 s | CPU-side evidence of waiting for a prior GPU submission. |
| `UsdContext::Impl::render` | ~2.63 s summed over many frames | USD/Hydra update work is present but does not explain a 20-second CPU compute block. |
| `Thread waiting...` | ~43.87 s summed across threads | Multiple threads wait concurrently; summed durations are not wall-clock time. |

## Conclusion and next action

The controlled A/B points away from NAS storage and toward the RTX/GPU path. The CPU trace shows the host blocked at CUDA/RTX submission completion; it cannot say which GPU kernel, texture upload, shader/pipeline operation, or GPU-memory stall caused that wait.

The next diagnostic should be a GPU-capable trace (Kit Tracy with GPU injection, or NVIDIA Nsight Systems/Graphics) over the same marker interval. The first questions for that trace are:

1. Is the GPU busy with texture/geometry upload, shader/pipeline compilation, or rendering?
2. Is there a VRAM-residency or allocation stall?
3. Does the long `waitForLastSubmission` correspond to one or several GPU submissions?

Do not prioritize local caching or NAS pre-copy until a repeated A/B run contradicts this result.
