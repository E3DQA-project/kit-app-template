# Findings

- Latest run: `STAGE_OPENED` 129 ms, `RENDER_STABLE` 7.726 s, `USD_ASSETS_LOADED` 27.336 s, `FIRST_USER_ACTION` 27.829 s.
- `RENDER_STABLE → USD_ASSETS_LOADED` is 19.610 s; `USD_ASSETS_LOADING → USD_ASSETS_LOADED` is 20.249 s in that run.
- Latest activity trace records `Render Thread / Post Sync` at 6.984 s and short MDL/material spans; it has no named activity for the rest of the wait.
- Prior CPU trace localizes about 20.7 s to `RtxHydraEngine::endFrame` / graphicsmux submission / `CommandList::waitForLastSubmission`.
- NAS/SSD medians are 20.681 s and 20.944 s, so storage is not the dominant explanation.
- GPU telemetry shows low utilization and ample VRAM; Vulkan/CUDA traces do not show a long ordinary GPU kernel or copy.
- Kit 110.2 plus async shader-finalization settings fixed startup PSO input lockup, not scene-loading overhead.
