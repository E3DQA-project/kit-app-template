# MOS first-user-action run — 2026-08-17

## Purpose

Measure a participant-facing upper bound for scene readiness. MOS records
`FIRST_USER_ACTION` when it receives the first key press, mouse-button press, or
scroll while navigation is active. In this run the deliberate action was `W`.

## Run

- App log: `/home/pierce/.nvidia-omniverse/logs/Kit/MOS App/0.1/kit_20260817_185542.log`
- Dataset: NAS-backed `/mnt/NAS/pierce/E3DQA_dataset/...`
- Scenes loaded: initial scene plus three Next transitions (generations 1–4).
- Action: participant pressed `W` after the new scene was visibly usable.

## Results

| Generation | Scene | Stage opened | First present | Post-present | Kit “stage has loaded” | First user action | Begin → action |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `generated_3dgs_opt.usdz` | 136 ms | 145 ms | 145 ms | 28,269 ms | 29,639 ms | 29.639 s |
| 2 | `generated_3dgs_opt_downsample_p0.25.usdz` | 149 ms | 156 ms | 157 ms | 22,350 ms | 22,762 ms | 22.762 s |
| 3 | `generated_3dgs_opt_downsample_p0.50.usdz` | 146 ms | 152 ms | 153 ms | 24,284 ms | 24,569 ms | 24.569 s |
| 4 | `generated_3dgs_opt_downsample_p0.75.usdz` | 136 ms | 147 ms | 147 ms | 25,744 ms | 26,298 ms | 26.298 s |

The app-side `FIRST_POST_LOAD_UPDATE` was 143–225 ms in the same run, so it is
not a visual-readiness signal. The first user action is an upper bound: it
includes the participant's small reaction delay. Still, it is the first marker
that closely follows the visible wait observed in the GUI.

## Strong correlation point

`nycu.my_usd_viewer_messaging_extension.stage_loading` emitted “stage has
loaded” 0.285–1.370 seconds before the participant pressed `W`. It is not yet a
formal MOS contract, but it tracks participant-visible readiness much more
closely than native present events. It should be investigated as a potential
loading-completion signal and correlated with GPU/Tracy profiling.

## Capture-sampling limitation and fix

The first implementation requested a viewport baseline successfully, but its
follow-up sampling tried to create an asyncio task directly from a renderer
callback. Kit dispatched that callback on `Dummy-1`, which has no asyncio event
loop. Therefore this run has **no valid `CAPTURED_VIEWPORT_FRAME` or
`RENDER_STABLE` result**.

The follow-up code change queues the capture work to a permanent Kit update
subscription before creating the asyncio task. It was unit-tested and rebuilt
after this run, but requires one more interactive validation run.
