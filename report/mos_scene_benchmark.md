# MOS Scene Loading Benchmark

Participant label: `benchmark`
Scenes measured: 7

| # | Scene | Mode | Disk at start | GPU standby | Transition (s) |
|---:|---|---|---|---|---:|
| 1 | `generated_3dgs_opt.usdz` | dual_slot_load | idle | False | 41.863 |
| 2 | `generated_3dgs_opt_downsample_p0.25.usdz` | gpu_swap | ready | True | 0.006 |
| 3 | `generated_3dgs_opt_downsample_p0.50.usdz` | gpu_swap | ready | True | 0.005 |
| 4 | `generated_3dgs_opt_downsample_p0.75.usdz` | gpu_swap | ready | True | 0.006 |
| 5 | `generated_3dgs_opt_spatial_noise_s0.0010.usdz` | gpu_swap | ready | True | 0.008 |
| 6 | `generated_3dgs_opt_spatial_noise_s0.0050.usdz` | gpu_swap | ready | True | 0.005 |
| 7 | `generated_3dgs_opt_spatial_noise_s0.0100.usdz` | gpu_swap | ready | True | 0.004 |
