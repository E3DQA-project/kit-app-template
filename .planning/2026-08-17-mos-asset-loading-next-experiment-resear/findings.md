# Findings & Decisions

## Requirements
- Commit and push the current checkpoint implementation before research. Completed as `733cb7a` on `origin/cleanup`.
- Investigate the record's proposed next experiment in detail and save findings in the wiki.

## Research Findings
- The latest run isolates `USD_ASSETS_LOADING → USD_ASSETS_LOADED` as 20.9–27.8 s.
- `STREAMING_IDLE` occurs at 1.9–7.2 s; the viewer's two post-idle updates take 16–18 ms.
- `get_stage_loading_status()` produced only a final empty snapshot in this run, so it did not identify the late asset.
- `omni.activity.profiler` is cached locally and provides `CAPTURE_MASK_SCENE_LOADING`, which emits USD scene-loading activity spans through the carb profiler backend. MOS does not currently declare it as an app dependency; add it only in the trace configuration.
- This Kit cache does not include a Tracy extension. The reproducible baseline is Kit’s built-in CPU trace backend; Tracy/GPU tracing is a follow-up only if that extension is made available.
- The MOS scene list can be overridden without code changes through `/exts/nycu.mos_app_extension/sceneListPath`, so an NAS and local-SSD JSON list can drive otherwise identical runs.
- NVIDIA’s Kit profiling guidance documents the CPU backend, Chrome trace capture, and optional Python profiling. Its activity-profiler documentation confirms the dedicated scene-loading capture mask.

## Technical Decisions
| Decision | Rationale |
|---|---|
| Do not optimize before an A/B and trace | The current marker identifies the phase, not the responsible subsystem. |

## Issues Encountered
| Issue | Resolution |
|---|---|
| Viewer instrumentation emits an empty-stage opening before each target opening | Match records by target USDZ filename; document the offset. |

## Resources
- `docs/records/2026-08-17-mos-asset-loading-checkpoints.md`
- `source/extensions/nycu.my_usd_viewer_messaging_extension/.../stage_loading.py`
