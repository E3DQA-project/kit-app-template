# MOS Vulkan profiler run — 2026-08-17

## Scope

Attempted a live GPU/Vulkan trace while loading MOS scenes from the NAS. The app was launched under NVIDIA Nsight Systems 2026.4.1 with Vulkan, OS runtime, and NVTX tracing enabled; CPU sampling was disabled because the host security policy blocks it.

The user loaded four scenes before quitting. Scene 3's first interaction is intentionally not a responsiveness measurement because the user paused before acting.

## Result: GPU trace invalid

No GPU timeline may be inferred from this run. On application exit, Nsight reported that Kit-created processes had been re-parented and continued waiting for them. Interrupting that wait left `/tmp/nsys-pierce/nsys-report-62ac.qdstrm` incomplete. Nsight rejected it during import, so no `.nsys-rep` was produced.

The next GPU attempt must use `--wait=primary` and a short single-scene run, so the collector finalizes as soon as the primary Kit process exits rather than waiting for its detached helpers. It should also use a bounded capture range once the app emits NVTX ranges; a full-app Vulkan trace noticeably perturbs scene timing.

## Valid lifecycle markers captured by Kit

The Kit log itself is valid: `/home/pierce/.nvidia-omniverse/logs/Kit/MOS App/0.1/kit_20260817_210429.log`.

| Scene | Render stable | USD assets loaded | Viewer stage loaded | First user action |
| --- | ---: | ---: | ---: | ---: |
| full | 20.591 s | 41.000 s | 41.019 s | 41.607 s |
| p0.25 | 4.080 s | 22.831 s | 22.849 s | 25.207 s |
| p0.50 | 7.196 s | 27.438 s | 27.457 s | 116.508 s (exclude: user paused) |
| p0.75 | 6.051 s | 26.594 s | 26.613 s | 27.193 s |

`RENDER_STABLE` continued to occur before `USD_ASSETS_LOADED`. The later `USD_ASSETS_LOADED` checkpoint remains the closest measured program-level boundary for the full load interval.

## Interpretation

This run confirms that the old CPU trace's RTX/GPU-wait suspicion is worth pursuing, but it does **not** quantify a GPU bottleneck. The full Vulkan profiler changed the timing substantially (especially the full scene), so these numbers must not be compared directly with unprofiled NAS/SSD runs.

## Next capture design

1. Add one NVTX range around the measured scene-loading interval.
2. Run the current Nsight CLI with `--wait=primary`, Vulkan workload tracing, CPU sampling disabled, and capture only that range.
3. Load one scene, quit normally, and import the finalized `.nsys-rep`.
4. Correlate Vulkan queue submissions, GPU workload durations, and CPU waits with the MOS markers.


## Follow-up: valid one-scene Vulkan trace

The follow-up run used the local SSD mirror and Nsight Systems with `--wait=primary`.
It produced a valid, inspectable report:

`_mos_asset_loading_experiment/mos_gpu_full_one_scene.nsys-rep` (32 MB)

The application exited normally. Nsight then spent a long time downloading optional debug-symbol files and displayed `Press Ctrl-C to stop symbol files downloading`. Interrupting at that *post-processing* prompt is safe: it aborts symbol download only and finalizes the report. Do not send Ctrl-C while the Kit application is still running.

### Lifecycle result

| Checkpoint | Elapsed from `BEGIN` |
| --- | ---: |
| `STAGE_OPENED` | 0.119 s |
| `RENDER_STABLE` | 7.674 s |
| `USD_ASSETS_LOADING` | 7.078 s |
| `USD_ASSETS_LOADED` | 27.143 s |
| `FIRST_USER_ACTION` | 27.675 s |

The measured asset-loading interval was **20.065 s** (`USD_ASSETS_LOADING` to `USD_ASSETS_LOADED`).

### Vulkan result and its limit

In the corresponding 20-second window, **Vulkan** performed about **2–5 ms of work per second**; its largest workload was a single **17.7 ms** burst near the start. Vulkan queue submits and fence waits were likewise only a few milliseconds per second. Vulkan pipeline creation was concentrated during application startup, not inside the asset-loading interval.

This is useful negative evidence about the Vulkan side of the renderer, but it does **not** clear the GPU/RTX path. The earlier CPU trace named the long blocking work `CUDA command` / `CUDA submit` and `RtxHydraEngine::endFrame`; this Nsight command did not trace CUDA. It therefore cannot show the CUDA kernels, CUDA uploads, or CUDA-side waits that may be responsible.

The controlled NAS/SSD A/B still makes storage bandwidth unlikely to be the primary cause. The next capture must use Nsight Systems with **CUDA plus Vulkan** tracing over the same single-scene run, then correlate CUDA work and synchronization with this exact lifecycle interval. Only if CUDA is also idle should the investigation move upstream to USD/3DGS CPU processing.

These elapsed times are from a profiled run, so they are diagnostic evidence rather than a performance benchmark.


## Follow-up: CUDA plus Vulkan trace and CPU-trace reconciliation

A second valid one-scene report was captured with Nsight tracing `cuda,vulkan,osrt,nvtx`:

`_mos_asset_loading_experiment/mos_cuda_vulkan_one_scene.nsys-rep` (31 MB)

It contains no CUDA kernel or CUDA memory-operation records. Its only substantial CUDA APIs are Vulkan/CUDA interoperability setup (`cudaImportExternalMemory`, `cudaExternalMemoryGetMappedMipmappedArray`, and related cleanup), totalling milliseconds. This rules out an ordinary CUDA runtime kernel or memcpy as the observed 20-second operation, but does not expose Kit's lower-level graphics-backend work.

The existing Kit CPU activity trace supplies the decisive boundary. During the measured scene-load interval it contains one nested 20.7-second operation:

```text
Executing task
  Submit (Render graph command list, render queue 0, device 0, submission index 0)
    CUDA submit       carb.graphicsmux/Submission.cpp:262
      CUDA command    carb.graphicsmux/Submission.cpp:332
        CommandList::waitForLastSubmission
                       carb.graphicsmux/CommandList.cpp:552
```

`CommandList::waitForLastSubmission` lasted **20.688 s**, nested inside `RtxHydraEngine::endFrame`. Therefore the delay is now localized to Kit RTX's graphicsmux render-graph submission synchronization, rather than ordinary USDZ file I/O, NAS/SSD bandwidth, Vulkan shader compilation, or normal CUDA-runtime kernels.

The remaining unknown is what the graphics backend is waiting for. A future run should sample GPU utilization/VRAM and use a graphics-driver-level tool (such as Nsight Graphics) while this submission is blocked. Do not repeat the same broad CUDA/Vulkan trace: it cannot see beneath this graphicsmux synchronization point.


## Follow-up: driver telemetry and single-GPU configuration

An unprofiled one-scene run recorded NVIDIA driver telemetry every 100 ms during `USD_ASSETS_LOADING` (19.749 s):

| Metric | Result |
| --- | ---: |
| GPU utilization | 5.0% mean; 19% maximum |
| VRAM use | 4.45–5.56 GB of 32 GB |
| Board power | 51.6–79.0 W |
| GPU-saturated samples (>=90%) | 0 of 197 |

The GPU was neither saturated nor memory-constrained while the graphicsmux submission wait occurred. Together with the near-constant ~20.7-second delay across SSD/NAS and multiple scene variants, this makes a fixed renderer-side synchronization/timeout path more likely than work proportional to scene bytes or GPU capacity.

MOS had `renderer.multiGpu.enabled = true` despite this machine exposing one GPU. The app configuration itself documents that a single-GPU context should set this value to false. It is now set to `false` in `source/apps/nycu.mos_app.kit`; the release build succeeded. The next clean, unprofiled one-scene run must compare its `USD_ASSETS_LOADING → USD_ASSETS_LOADED` duration with the prior ~20.7-second baseline before any further renderer changes.


## Single-GPU A/B result

The clean, unprofiled one-scene run after setting `renderer.multiGpu.enabled = false` measured:

| Configuration | `USD_ASSETS_LOADING → USD_ASSETS_LOADED` |
| --- | ---: |
| Matched SSD baseline (multi-GPU enabled) | 20.852 s |
| Single-GPU configuration | 19.591 s |
| Difference | -1.261 s (-6.0%) |

Disabling the incorrect multi-GPU configuration modestly improved the interval but did not remove the nearly fixed ~20-second renderer-side wait. Keep the correct single-GPU setting; it is not the primary fix.
