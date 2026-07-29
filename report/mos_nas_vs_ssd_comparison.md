# MOS NAS versus Local SSD Benchmark

**Date:** 2026-07-28  
**Scenes:** 7 from `source/data/mos_scenes.json`  
**Mode:** headless, non-interactive, GPU-resident dual-slot benchmark

## Executive result

Changing the manifest from `/mnt/NAS/...` to `/mnt/gen5_SSD/...` improved the cold first scene load from **41.863 s** to **29.884 s** (**28.6% faster**). This proves NAS/NFS I/O is a meaningful part of cold preparation.

It did **not** materially change the user-visible transition behavior: after preparation, both runs swapped GPU-resident scenes in only a few milliseconds. The remaining cold-load cost is therefore in USD stage loading, scene composition, Hydra/RTX synchronization, and GPU upload—not simply copying bytes from storage.

## Side-by-side timings

| Measurement | NAS/NFS | Local SSD | Change |
|---|---:|---:|---:|
| Cold first active load | 41.863 s | 29.884 s | 28.6% faster |
| Median visible GPU swap (scenes 2–7) | 0.0053 s | 0.0034 s | 35.4% lower |
| Median disk preload | 9.65 s | 1.10 s | 88.6% faster |
| Median GPU standby preparation | 0.30 s | 0.30 s | 0.0% lower |

## Scene-by-scene visible transition

| # | Scene | NAS transition | SSD transition |
|---:|---|---:|---:|
| 1 | `generated_3dgs_opt.usdz` | 41.863 s | 29.884 s |
| 2 | `generated_3dgs_opt_downsample_p0.25.usdz` | 0.006 s | 0.008 s |
| 3 | `generated_3dgs_opt_downsample_p0.50.usdz` | 0.005 s | 0.003 s |
| 4 | `generated_3dgs_opt_downsample_p0.75.usdz` | 0.006 s | 0.003 s |
| 5 | `generated_3dgs_opt_spatial_noise_s0.0010.usdz` | 0.008 s | 0.003 s |
| 6 | `generated_3dgs_opt_spatial_noise_s0.0050.usdz` | 0.005 s | 0.005 s |
| 7 | `generated_3dgs_opt_spatial_noise_s0.0100.usdz` | 0.004 s | 0.003 s |

## Preparation timings

| Scene | NAS disk preload | SSD disk preload | NAS GPU standby | SSD GPU standby |
|---|---:|---:|---:|---:|
| `generated_3dgs_opt_downsample_p0.25.usdz` | 2.8 s | 0.5 s | 4.7 s | 4.2 s |
| `generated_3dgs_opt_downsample_p0.50.usdz` | 5.7 s | 0.7 s | 0.3 s | 0.3 s |
| `generated_3dgs_opt_downsample_p0.75.usdz` | 8.6 s | 1.0 s | 0.3 s | 0.3 s |
| `generated_3dgs_opt_spatial_noise_s0.0010.usdz` | 10.7 s | 1.3 s | 0.3 s | 0.3 s |
| `generated_3dgs_opt_spatial_noise_s0.0050.usdz` | 13.4 s | 8.6 s | 0.3 s | 0.3 s |
| `generated_3dgs_opt_spatial_noise_s0.0100.usdz` | 10.7 s | 1.2 s | 0.3 s | 0.3 s |

## Interpretation

- **NAS/NFS is significant for preparation.** Lookahead copies became sub-second to low-single-digit seconds on SSD in most cases, compared with multi-second NAS copies.
- **NAS/NFS is not the main visible-transition bottleneck once staging is enabled.** GPU swaps remained approximately 3–8 ms in both runs.
- **Rendering/scene preparation remains the dominant cold-load component.** SSD reduced the first active load by about 12 seconds, but the SSD load still took about 30 seconds.
- **The interactive GUI path is exposing preparation to the participant.** The benchmark hides disk, USD, Hydra, and GPU work in the background and leaves only the prepared-slot activation in the subjective interval.

## Limitations

This is one run per storage location, not a repeated statistical experiment. The NAS run used the NFS mount `140.113.203.131:/volume1/lab-workstation`; the SSD run used `/dev/nvme0n1`. CPU power mode, OS cache state, GPU state, and system load were not locked between runs. The numbers establish the direction and pipeline behavior, but repeated cold-cache runs are needed for a precise percentage attribution.

## Bottom line

**Moving the assets to the SSD helps materially, especially for background preloading, but it does not explain all of the original 20–25 second GUI delay. The robust solution remains: local SSD assets plus asynchronous disk preload plus GPU-resident dual-slot staging.**

Raw logs: `kit_20260728_231126.log` (NAS) and `kit_20260728_232918.log` (SSD).
