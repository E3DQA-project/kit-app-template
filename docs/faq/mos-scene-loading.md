# MOS scene-loading FAQ

## Why do the logs say the scene is ready in a few milliseconds when I wait 20–30 seconds?

They are measuring different things. MOS can finish opening the stage, positioning the camera, and show a stable-looking early frame quickly. Kit can still be preparing the scene in the background. The participant-visible completion point is closer to `USD_ASSETS_LOADED` and the viewer’s final “stage loaded” message, not `STAGE_OPENED` or `RENDER_STABLE`.

## Does loading from disk happen before `RENDER_STABLE`?

Some of it does, but “disk loading” is not one isolated step. Kit can read enough data to render an early stable frame while it continues resolving assets, preparing materials, creating GPU resources, and waiting on the RTX pipeline. `USD_ASSETS_LOADING → USD_ASSETS_LOADED` is a broad asset-readiness interval, not a stopwatch for reading one USDZ file.

## Why did the first timing records look much shorter than the delay I saw in the GUI?

The original markers stopped at an early renderer or stage-open checkpoint. They did not prove that all scene assets were ready for interaction. The later viewer markers and first-input marker showed the real gap: the scene could appear stable after a few seconds but remained in the asset-loading lifecycle for about 20 seconds longer.

## What does `FIRST_USER_ACTION` mean? Is it load time?

No. It records the first keyboard or mouse action after a scene becomes usable. It is a useful validation that the participant could interact, but it includes human reaction time. Use `VIEWER_STAGE_LOADED` for application readiness and `FIRST_USER_ACTION` as a user-experience cross-check.

## Did moving the 1 GB USDZ files from NAS to SSD help?

Not in the first controlled run. For four byte-identical scenes with matching camera metadata, the median `USD_ASSETS_LOADING → USD_ASSETS_LOADED` duration was 20.68 s from NAS and 20.94 s from SSD. That means plain file location is not the first bottleneck to optimize.

A NAS can still be fast because it or Linux may cache data in RAM, and the measured interval includes much more than file reads. The test was app-cold, not a forced disk-cold benchmark, so it does not claim the NAS is intrinsically faster than the SSD.

## What did the CPU trace show?

The trace hook captured exactly the slow asset-loading interval. During it, the host spent about 20.7 seconds in RTX/CUDA submission-completion and command-list wait spans. This is evidence that the CPU is waiting on the RTX/GPU path, not spending 20 seconds doing ordinary Python or USD CPU work.

It is not yet a GPU kernel breakdown. A CPU trace cannot identify whether the GPU is busy with texture upload, shader compilation, memory residency, or rendering.

## What happens next?

Capture a GPU-capable timeline over the same markers using Kit Tracy with GPU injection or NVIDIA Nsight. The aim is to distinguish texture/geometry upload, shader or MDL compilation, VRAM allocation/eviction, and normal rendering work. The full method and first results are in [the NAS/SSD and CPU-trace record](../records/2026-08-17-mos-nas-ssd-and-cpu-trace.md).

## Can asynchronous or parallel loading still make scene changes faster?

Potentially, yes—but only after the GPU trace tells us what resources are limiting the current load.

If the limit is CPU decoding or archive work, parallel preparation may help. If it is shader compilation, warming the shader/material cache may help. If it is GPU uploads or VRAM pressure, loading the next scene in parallel could make the current scene worse by competing for GPU memory.

A likely eventual design is double-buffered preloading: keep the current scene interactive, prepare the next scene in an isolated context, and swap only when it is genuinely ready. That needs careful GPU-memory budgeting and a trace-backed decision first.

## Why did an SSD experiment have to be repeated?

The first SSD mirror omitted a sibling `geom_optim/output/cameras.json` file. MOS therefore used its fallback camera, unlike the NAS run. The result was excluded, the metadata was copied with its hash verified, and the SSD baseline was repeated. This is why controlled comparisons must preserve the complete scene setup, not only the USDZ bytes.
