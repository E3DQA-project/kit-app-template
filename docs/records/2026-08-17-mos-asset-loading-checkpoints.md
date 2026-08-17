# MOS asset-loading checkpoint run — 2026-08-17

## Purpose

Split the remaining participant-visible delay using the viewer's actual completion state machine.

## Run

- App log: `/home/pierce/.nvidia-omniverse/logs/Kit/MOS App/0.1/kit_20260817_192700.log`
- Dataset: NAS-backed `/mnt/NAS/pierce/E3DQA_dataset/...`
- Scenes: initial scene plus three Next transitions (MOS generations 1–4).
- New viewer checkpoints: `USD_OPENING`, `USD_ASSETS_LOADING/LOADED`,
  `STREAMING_BUSY/IDLE`, two post-idle updates, and `VIEWER_STAGE_LOADED`.
- Action: participant pressed `W` once the scene was usable.

## Results

| MOS scene | Viewer busy | Viewer idle | Assets loading | Assets loaded | Assets-loading duration | Viewer final completion | First W |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 131 ms | 7,248 ms | 200 ms | 27,989 ms | 27,789 ms | 28,007 ms | 28,453 ms |
| 2 | 233 ms | 1,951 ms | 1,951 ms | 23,053 ms | 21,102 ms | 23,071 ms | 23,550 ms |
| 3 | 213 ms | 3,624 ms | 3,625 ms | 24,509 ms | 20,884 ms | 24,527 ms | 24,879 ms |
| 4 | 230 ms | 5,338 ms | 5,339 ms | 26,423 ms | 21,084 ms | 26,441 ms | 26,929 ms |

All values are aligned to the MOS `BEGIN` timestamp. Viewer events were matched by target USDZ filename; the viewer also emits an expected empty-stage `USD_OPENING` during MOS teardown, which is excluded from this table.

## Decisive finding

```text
STREAMING_IDLE                 1.9–7.2 s
USD_ASSETS_LOADING → LOADED   20.9–27.8 s   ← dominant delay
post-idle updates              16–18 ms
VIEWER_STAGE_LOADED → W       0.35–0.48 s
```

The earlier hypothesis was incomplete. `STREAMING_IDLE` occurs well before final readiness, so the viewer's wait is not dominated by an active streaming manager. It is dominated by the USD asset-loading phase, which remains active until `ASSETS_LOADED`.

The stage-loading-status API returned only an empty final snapshot (`files_loaded=0`, `total_files=0`) when sampled at `ASSETS_LOADED`; it did not expose useful per-file progress during this run. The forwarded activity/progress events did show MDL activity at startup, but did not name the long late asset operation. A CPU/GPU trace or lower-level asset resolver/MDL instrumentation is required to identify that operation.

## What is not the bottleneck

- MOS camera/orientation/nav work: about 0.13–0.17 s.
- First present / stable captured image: about 2.5–7.8 s.
- Viewer post-idle policy: two updates, about 16–18 ms.
- Participant input after viewer completion: about 0.35–0.48 s.

## Next target

Profile `USD_ASSETS_LOADING → USD_ASSETS_LOADED` specifically. Compare the same USDZs on NAS and local SSD, then capture a Kit/Tracy CPU+GPU trace. The objective is to identify whether this phase is asset I/O, USDZ archive handling, MDL/material processing, texture loading, GPU upload, or another asynchronous dependency.
