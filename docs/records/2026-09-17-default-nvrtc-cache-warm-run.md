# MOS default NVRTC cache — warm run (2026-09-17)

## Purpose

Verify that a second normal local MOS launch reuses the artifact created by the
valid cold run, without repeating NVRTC compilation.

## Setup

- Command: `./repo.sh launch nycu.mos_app.kit`
- Same user-owned `source/data/mos_scenes.json` as the cold run.
- Cache mode: default automatic mode (`MOS_V2_MODE=auto`).
- Cache root: `/mnt/gen5_SSD/pierce/mos-nvrtc-cache-v2/`.

## Observed cache lifecycle

| Checkpoint | Timestamp / duration | Evidence |
| --- | --- | --- |
| Kit app ready | 2.982 s after Kit launch | terminal output |
| Cache program tracked | epoch 1789638769892176136 ns | `MOS_V2 event=tracked` |
| Cached PTX returned | epoch 1789638770224996646 ns | `MOS_V2 event=hit` |
| `tracked` to `hit` | about 333 ms | epoch timestamp difference |
| Lowered names restored | five `name_hit` events | terminal output |
| Repeated NVRTC compile | none | no `compile_begin`, `compile`, or `stored` event |

The restored lowered names were `preProcessParticles`, `projectOnTiles`,
`expandTileProjections`, `render`, and `prepareScene`.

## User-visible validation

The user accepted this as a successful GUI run after confirming the app was
usable. The process reached scene loading and then exited normally.

## Result

The ordinary MOS launch now reuses the same-scene-list NVRTC output on a warm
run. This removes the measured 18.952-second NVRTC compile from this portion of
the loading lifecycle. It does not claim to remove other USD, renderer, or
scene-dependent loading costs.
