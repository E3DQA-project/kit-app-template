# MOS default NVRTC cache — cold run (2026-09-17)

## Purpose

Validate that the normal local MOS command uses the NVRTC cache automatically,
after wiring the repository-owned launch tool into the live `repo launch`
configuration.

## Setup

- Command: `./repo.sh launch nycu.mos_app.kit`
- Cache mode: default (`MOS_V2_MODE=auto`); no manual preload or experiment
  command was supplied.
- Cache location: `/mnt/gen5_SSD/pierce/mos-nvrtc-cache-v2/`
- Scene-list scope: current user-owned `source/data/mos_scenes.json`.
- GPU: NVIDIA GeForce RTX 5090.

## Observed cache lifecycle

| Checkpoint | Timestamp / duration | Evidence |
| --- | --- | --- |
| Kit app ready | 2.895 s after Kit launch | terminal output |
| Scene 1/10 requested | about 13 s after Kit launch | MOS status log |
| NVRTC program tracked | epoch 1789638545900567918 ns | `MOS_V2 event=tracked` |
| NVRTC compile began | epoch 1789638545919710355 ns | `MOS_V2 event=compile_begin` |
| NVRTC compile returned | 18,952 ms | `MOS_V2 event=compile result=0 ms=18952` |
| PTX artifact stored | epoch 1789638564999117572 ns | `MOS_V2 event=stored` |

The stored artifact is `6,577,549` bytes. The compiled shim is stored
alongside it in the same dedicated SSD cache root.

## User-visible validation

The user confirmed that the scene was visible and the camera could be moved
before closing the app. This is therefore a valid cold-cache run, not merely a
terminal-level cache event.

## Result

The cache is now integrated into the real local MOS launch route. This first
run compiled once and persisted the result. The next run must use the same
scene list and show `MOS_V2 event=hit` rather than another ~19-second compile.
