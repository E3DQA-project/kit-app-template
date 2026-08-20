# MOS scene-loading FAQ

## Why do the logs say the scene is ready in a few milliseconds when I wait 20–30 seconds?

They measure different boundaries. `STAGE_OPENED`, camera setup, and MOS's early renderer callbacks happen quickly. Kit can still be waiting for late asset and RTX/graphics work. The participant-facing interval is closer to `VIEWER_STAGE_LOADED` and the first deliberate input than to `STAGE_OPENED`.

## Does `RENDER_STABLE` mean the scene is completely rendered and interactable?

No. It means the captured viewport image passed the stability test. In the latest run, `RENDER_STABLE` occurred at 7.726 seconds, while `USD_ASSETS_LOADED` occurred at 27.336 seconds and the first `W` input at 27.829 seconds.

## What exactly happens during the missing 20 seconds?

The current traces do not expose a named operation for all of it. The detailed latest sequence is:

- MDL activity messages report progress `1.0` around +7.09 seconds.
- Three viewport samples confirm a stable image by +7.726 seconds.
- No detailed Kit activity checkpoint appears until `USD_ASSETS_LOADED` at +27.336 seconds.
- The viewer gate clears 3 ms later and reports the stage loaded 14 ms after that.

A CPU trace from an earlier matched run shows a roughly 20.7-second RTX graphicsmux `CommandList::waitForLastSubmission` nested inside `RtxHydraEngine::endFrame`. This strongly points to a graphics-backend synchronization/completion wait, but it does not identify what the backend or driver is waiting for.

## Is the USDZ file slow to open?

Not according to the measured boundary. The latest `omni.usd` log reported the USDZ opened successfully in about 2 ms, and `BEGIN → STAGE_OPENED` was 129 ms. The file-open boundary is not where the 20-second delay appears.

## Did loading from the SSD help compared with the NAS?

Not consistently. The matched median was 20.681 s from NAS and 20.944 s from SSD. The SSD was not faster overall. The experiment was app-cold, not a forced disk-cold benchmark, and the measured interval includes much more than raw file reads.

## Is the GPU overloaded or out of VRAM?

The telemetry says no for the measured run: GPU utilization averaged 5%, peaked at 19%, and VRAM stayed between 4.45 and 5.56 GB of 32 GB. This does not rule out a driver or synchronization problem, but it argues against ordinary saturation or memory exhaustion.

## Did Vulkan or CUDA show a 20-second workload?

No. Vulkan showed only a few milliseconds of work per second, and the CUDA-plus-Vulkan report contained no long CUDA kernel or memory-copy operation. The CPU trace still showed Kit waiting in the RTX graphics submission path, which is a lower-level boundary than those traces exposed.

## Is this definitely an RTX 5090 bug?

Not proven. The machine uses an RTX 5090 and the evidence is compatible with a Blackwell/driver/Kit graphics-backend interaction, but the current measurements cannot isolate the driver as the cause. A driver-level graphics trace is needed before making that claim.

## What did the Kit upgrade fix?

Kit was upgraded from 110.0.0 to 110.2.0. A cold-start PSO compilation hang prevented the participant prompt from accepting input. Asynchronous shader-finalization settings removed that startup hang and restored a usable prompt at roughly 3 seconds. The scene's later 20-second loading delay remained.

## Did disabling multi-GPU fix the problem?

No. It improved one matched SSD run from 20.852 s to 19.591 s, about 6%, but did not remove the nearly fixed delay. It remains the correct configuration for this single-GPU machine, but it is not the primary bottleneck.

## Can parallel or asynchronous scene loading fix it?

Maybe, but not safely yet. CPU decompression or preparation could benefit from overlap. GPU uploads, VRAM residency, or a serialized RTX fence could become slower if another scene competes for the same resources. We need to identify the blocked operation first.

## What is the next useful experiment?

Run one scene with a narrow driver-level graphics trace covering exactly `USD_ASSETS_LOADING → USD_ASSETS_LOADED`, while retaining the MOS markers. The goal is to identify whether the missing time is a driver fence, graphicsmux submission, resource upload, residency operation, or another backend wait.

## Where are the detailed documents?

Start with [the current knowledge page](../wiki/mos-scene-loading-current-knowledge.md) and [the consolidated evidence record](../records/2026-08-20-mos-scene-loading-consolidated.md). Historical runs remain in the [records directory](../records/).
