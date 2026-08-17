# MOS capture and first-user-action run — 2026-08-17

## Purpose

Validate the repaired swapchain-capture path and time each available phase from
`BEGIN` to the participant's first deliberate navigation action.

## Run

- App log: `/home/pierce/.nvidia-omniverse/logs/Kit/MOS App/0.1/kit_20260817_190509.log`
- Dataset: NAS-backed `/mnt/NAS/pierce/E3DQA_dataset/...`
- Scenes: initial scene plus three Next transitions (generations 1–4).
- Controlled action: `W` was pressed once the scene was visibly usable.
- Capture rule: four default-window swapchain samples, fifteen Kit updates apart;
  `RENDER_STABLE` after two consecutive sampled mean-byte deltas were at most 3.

## All measured milestones

| Generation | Scene | Stage opened | Nav ready | First present | First capture | Render stable | RTX view assigned | Viewer “stage has loaded” | First W |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `generated_3dgs_opt.usdz` | 128 ms | 133 ms | 140 ms | 7,495 ms | 7,826 ms | 7,264 ms | 27,954 ms | 28,459 ms |
| 2 | `generated_3dgs_opt_downsample_p0.25.usdz` | 159 ms | 162 ms | 209 ms | 2,109 ms | 2,444 ms | 1,929 ms | 22,679 ms | 23,141 ms |
| 3 | `generated_3dgs_opt_downsample_p0.50.usdz` | 147 ms | 150 ms | 193 ms | 3,848 ms | 4,271 ms | 3,662 ms | 24,392 ms | 24,744 ms |
| 4 | `generated_3dgs_opt_downsample_p0.75.usdz` | 141 ms | 146 ms | 146 ms | 5,595 ms | 5,947 ms | 5,377 ms | 25,959 ms | 26,530 ms |

All values are elapsed from that generation's `BEGIN`.

## What each gap says

```text
BEGIN → STAGE_OPENED                 128–159 ms  USDZ stage becomes active
STAGE_OPENED → NAV_READY               3–5 ms    MOS orientation/camera work
BEGIN → first swapchain capture     2.109–7.495 s  first accessible window image
capture → RENDER_STABLE               0.331–0.423 s  sampled image stops changing
RENDER_STABLE → viewer stage loaded 19.780–20.128 s  major unexplained wait
viewer stage loaded → first W         0.352–0.505 s  participant reaction / input
```

The last two lines are the strongest result. The app's own loading-completion
message tracks the participant-visible point closely, while the stable swapchain
image arrives about twenty seconds too early.

## Interpretation and limitations

- `FIRST_PRESENT_TO_VIEWPORT`, `POST_PRESENT_FRAME_BUFFER`, and a stable
  swapchain image do **not** prove the new scene is usable. They can describe a
  stale or incomplete viewport image.
- The successful baseline comparisons for generations 2–4 (`baseline_delta` 94,
  66, and 87) confirm that the later sampled image differed from the captured
  starting image. The later samples had `mean_delta=0`.
- Generation 1 had `baseline_delta=0`; its baseline likely arrived after the
  new image was already on screen, so it cannot prove a visual transition.
- `FIRST_RENDER_COMMAND` and `FIRST_DISPLAYABLE_RENDER_FRAME` still did not
  appear. They occur before the observer can be armed for this stage-open path,
  so they are not usable checkpoints in the current design.
- The viewer message is from `nycu.my_usd_viewer_messaging_extension`, not a
  documented generic Kit renderer-completion API. It is currently the best
  observed correlation point, not yet proof of the underlying bottleneck.

## Next investigation target

Instrument or trace the ~20 s interval:

```text
RENDER_STABLE
  → nycu.my_usd_viewer_messaging_extension "stage has loaded"
  → FIRST_USER_ACTION
```

That interval should be profiled with Kit/Tracy CPU+GPU tracing and by inspecting
what the viewer messaging extension waits for before it announces stage loaded.
