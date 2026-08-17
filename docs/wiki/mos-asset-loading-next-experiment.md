# MOS asset-loading: next experiment

## Why this is next

The latest checkpoint run narrowed the participant-visible delay to a single interval:

```text
USD_ASSETS_LOADING → USD_ASSETS_LOADED = 20.9–27.8 seconds
```

`STREAMING_IDLE` happens much earlier, the viewer's final two-update policy costs only 16–18 ms, and first input follows final viewer completion by about 0.35–0.48 s. The measured facts are in the [asset-loading checkpoint record](../records/2026-08-17-mos-asset-loading-checkpoints.md).

That interval is still a label, not an explanation. It can include reading from NAS, resolving references, unpacking a USDZ archive, composing USD, processing MDL/materials, decoding textures, uploading resources to GPU, or waiting for another asynchronous dependency. The next experiment is designed to distinguish those possibilities before changing scene content or loading code.

## The experiment has two separate runs

Do not combine the performance comparison and heavy tracing in one result. Profiling changes timing, so each run answers one question.

| Run | Question | Keep | Change | Primary result |
|---|---|---|---|---|
| A. Storage A/B baseline | Is getting the asset data the major cost? | Same build, four scenes, order, resolution, GPU, and MOS markers | NAS list versus local-SSD mirror list | Median `USD_ASSETS_LOADING → USD_ASSETS_LOADED` per source |
| B. Scene-loading CPU trace | Which subsystem consumes or waits during the slow interval? | One representative source and the same scene sequence | Enable CPU profiler + USD scene-loading activity spans | Named work on the timeline, correlated with the MOS markers |

Run A first. A large NAS-to-SSD improvement changes the direction of the investigation immediately. Run B then explains whatever remains, instead of producing a complicated trace that may include network delay.

## Run A: controlled NAS versus local SSD

### Setup

1. Pick the same four target USDZs used in the last record. Keep their order fixed inside a replica, but alternate which source runs first: NAS/SSD/NAS/SSD/... This limits the risk that run order is mistaken for a storage result.
2. Create a local-SSD mirror that preserves the assets' relative layout. If a USDZ is not self-contained, copy its complete dependency closure too—not merely the top-level USDZ.
3. Verify NAS and SSD copies before testing. Record the source paths and SHA-256 hashes of the top-level files (and dependency manifest, if applicable). A fast but different scene is not a valid result.
4. Produce two scene-list JSON files with the same scene identities but different URLs: one NAS-backed and one SSD-backed. MOS already supports this runtime override through `/exts/nycu.mos_app_extension/sceneListPath`; no code edit is needed.
5. Launch each list explicitly, for example:

   ```bash
   ./repo.sh launch nycu.mos_app.kit -- \
     --/exts/nycu.mos_app_extension/sceneListPath=/absolute/path/mos_scenes_ssd.json
   ```

6. Run at least three replicas for each source. Quit and relaunch MOS between replicas. Call this **app-cold**, not true disk-cold: Linux filesystem cache may still retain data. Do not force-clear OS caches; that requires elevated privileges and creates an artificial workload unlike normal use.

### What to record

For every scene and every replica, preserve the existing MOS and viewer markers. The comparison metric is:

```text
asset-load duration = USD_ASSETS_LOADED - USD_ASSETS_LOADING
```

Also retain `USD_OPENING`, `STREAMING_BUSY/IDLE`, `VIEWER_STAGE_LOADED`, `FIRST_USER_ACTION`, source (NAS/SSD), replica number, and app-log path. Summarize each scene using median and min–max; do not make a decision from one outlier.

### How to interpret it

| Result | Meaning | Likely next optimization |
|---|---|---|
| SSD is much faster | I/O, asset resolution, or USDZ/archive reads are a material contributor. | Local cache/mirror, pre-copy next scene, fewer external references, or a more efficient package layout. |
| SSD changes little and CPU is busy | Storage is not dominant; preparation work is local. | Inspect trace for USD composition, archive decompression, MDL, texture decode, or shader work. |
| SSD changes little and GPU/memory work dominates later tracing | Upload/residency is likely the limit. | Reduce texture/geometry working set, use LODs, reuse GPU resources, or prefetch. |
| Results vary wildly on the same source | The test is not controlled enough yet. | Check cache state, concurrent NAS traffic, shader-cache warmup, GPU memory pressure, and scene equivalence. |

## Run B: trace the interval, rather than guessing

### What is available in this build

Kit's CPU profiler backend can save a Chrome-compatible trace. NVIDIA documents the relevant backend settings in the [Kit profiling guide](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/profiling.html).

The local extension cache also contains `omni.activity.profiler`. Its `CAPTURE_MASK_SCENE_LOADING` mode is specifically for USD scene-loading activity and sends activity spans through Kit's profiler backend; see the [activity-profiler overview](https://docs.omniverse.nvidia.com/kit/docs/omni.activity.profiler/latest/Overview.html). MOS does **not** currently declare this extension, so enable it only for the trace experiment (or add it to a temporary profiling app configuration). This avoids changing ordinary timing runs.

This build does not currently have a Tracy extension in its extension cache. Therefore do not promise a GPU/Tracy result for the immediate next run. If Tracy is later added, NVIDIA documents its setup and optional GPU injection in the [Tracy extension guide](https://docs.omniverse.nvidia.com/extensions/latest/ext_profiler_tracy.html).

### Capture recipe

1. Keep the normal build and use one representative source from Run A—prefer local SSD if NAS is proven slow, otherwise use the normal NAS source.
2. Start a CPU trace from launch. NVIDIA's documented settings translate to this reproducible form:

   ```bash
   ./repo.sh launch nycu.mos_app.kit -- \
     --enable omni.activity.profiler \
     --/app/profilerBackend=cpu \
     --/app/profileFromStart=true \
     --/plugins/carb.profiler-cpu.plugin/saveProfile=true \
     --/plugins/carb.profiler-cpu.plugin/compressProfile=true \
     --/plugins/carb.profiler-cpu.plugin/filePath=/absolute/path/report/mos-asset-load-cpu-trace.gz
   ```

3. Enable `CAPTURE_MASK_SCENE_LOADING` in a small temporary diagnostic hook before requesting a scene, and disable its returned token immediately after `USD_ASSETS_LOADED`. The local API is `enable_capture_mask(mask)` and `disable_capture_mask(token)`. This adds USD scene-loading spans while avoiding a full-session activity capture.
4. Load the same target scene(s), then quit normally so Kit writes the trace. Open the resulting `.gz` trace in Chrome's tracing viewer or the Kit profiler window.
5. Correlate the trace with the app log using the existing `USD_ASSETS_LOADING` and `USD_ASSETS_LOADED` lines. Only analyze activity inside that window. Optional Python profiling (`CARB_PROFILING_PYTHON=1`) is useful only in a second trace if the CPU trace points at extension Python; it adds overhead and should not be used for baseline numbers.

### What to look for in the trace

| Timeline pattern during `USD_ASSETS_LOADING → USD_ASSETS_LOADED` | Probable owner | Next evidence / action |
|---|---|---|
| Long reads, resolver waits, or little CPU work while threads wait | Storage, asset resolver, or archive access | Compare NAS/SSD result; list referenced files and resolver paths. |
| One or more CPU cores busy in USD composition or archive work | USD composition or USDZ decompression | Reduce references/layers; test unpacked USD plus local assets; simplify package structure. |
| Work named MDL, material translation, texture processing, or shader compilation | Materials and textures | Audit material count, texture size/formats, MDL graph complexity, and shader-cache behavior. |
| GPU-copy / upload spans, VRAM growth, or stalls after CPU preparation | Texture/geometry upload and residency | Reduce working set, prefetch, change texture streaming policy only after measurement. |
| Long gap with neither useful CPU work nor GPU activity | Another serialized or external dependency | Add narrower resolver/asset callbacks; inspect loading activity payloads and network/filesystem telemetry. |

## Success condition

This investigation is successful when the next record can say one of the following with evidence:

- “Moving the identical scene closure from NAS to SSD removes X seconds, so data access/package layout is the first target.”
- “Storage changes little; the trace assigns most of the interval to a named CPU or GPU subsystem, so that subsystem is the first target.”
- “Neither explains it; the trace shows a wait, and the next instrumentation point is the specific resolver or dependency responsible.”

Only after that should we modify loading behavior, preloading, scene structure, material settings, or GPU streaming budgets.

## Relationship to existing diagnostics

- [Timing lifecycle and user-visible meaning](mos-scene-loading-timing.md)
- [Renderer readiness signals](mos-renderer-readiness-signals.md)
- [Post-render and streaming checkpoints](mos-post-render-streaming-checkpoints.md)
- [Latest measured checkpoint record](../records/2026-08-17-mos-asset-loading-checkpoints.md)
