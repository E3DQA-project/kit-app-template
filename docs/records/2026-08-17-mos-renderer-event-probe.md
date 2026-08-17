# MOS renderer-event probe — 2026-08-17

## Purpose

Test whether Kit's native renderer lifecycle events explain the participant-visible scene-loading delay after the MOS app reports `STAGE_OPENED`.

## Run

- App log: `/home/pierce/.nvidia-omniverse/logs/Kit/MOS App/0.1/kit_20260817_184112.log`
- Dataset location: NAS-backed `/mnt/NAS/pierce/E3DQA_dataset/...`
- Scenes: initial scene plus three Next transitions (generations 1–4).
- Instrumentation: `FIRST_POST_LOAD_UPDATE`, `FIRST_PRESENT_TO_VIEWPORT`, and `POST_PRESENT_FRAME_BUFFER` using `omni.kit.renderer.core` event streams.

## Results

| Generation | Scene | `STAGE_OPENED` | First post-load update | First viewport present | Post-present frame | First later RTX viewport assignment | Gap: Begin → later RTX assignment |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `generated_3dgs_opt.usdz` | 128 ms | 135 ms | 138 ms | 138 ms | 7,193 ms | 7,193 ms |
| 2 | `generated_3dgs_opt_downsample_p0.25.usdz` | 170 ms | 186 ms | 181 ms | 181 ms | 1,908 ms | 1,908 ms |
| 3 | `generated_3dgs_opt_downsample_p0.50.usdz` | 124 ms | 138 ms | 141 ms | 141 ms | 3,537 ms | 3,537 ms |
| 4 | `generated_3dgs_opt_downsample_p0.75.usdz` | 141 ms | 155 ms | 146 ms | 146 ms | 5,228 ms | 5,228 ms |

The RTX assignment marker is the first `rtx.multigpumanager.plugin` “View 0 … assigned to device 0” message **after** each generation's `BEGIN`. It is a diagnostic correlation, not a supported readiness event.

## What this proves

1. `FIRST_POST_LOAD_UPDATE` is only an app-loop marker.
2. The native renderer events are live and usable in Kit 110 after the compatibility fix.
3. A normal viewport-present/post-present event can occur in 138–181 ms, well before the later RTX viewport activity. Therefore it proves only that Kit presented *a* frame, not that the new scene is visibly complete.
4. The later RTX marker is a better lead for the multi-second overhead, but it still does not prove visual completion.

## Important limitations

- `FIRST_RENDER_COMMAND` and `FIRST_DISPLAYABLE_RENDER_FRAME` were not recorded. The subscriptions are currently armed after `NAV_READY`; those earlier renderer events can already have happened by then. Arm them earlier in the next instrumentation pass.
- This run contains no `CAPTURED_VIEWPORT_FRAME`, no visual-stability test, and no user-input marker. It cannot report the exact point at which the scene became fully usable.
- The gaps between one `BEGIN` and the next include participant time. They must not be interpreted as loading duration.

## Next experiment

1. Arm renderer subscriptions immediately when the target stage opens, before camera/UI post-load work.
2. Add a generation-safe swapchain or viewport-texture capture callback after the first post-present event.
3. In a controlled run with a stationary camera, sample a small number of captured frames and record `RENDER_STABLE` once successive frames stop changing materially.
4. Correlate that interval with a Kit GPU/Tracy profile to identify upload, shader, SceneDB, or GPU queue work.
