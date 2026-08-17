# MOS Renderer Readiness Signals: Detailed Reference

## Purpose

This page explains what MOS can measure after its own setup is complete and before the participant sees a usable new scene. It exists because an application update is not the same thing as a rendered frame.

Use the short overview first: [Understanding MOS Scene Loading Times](mos-scene-loading-timing.md).

## The four meanings of “ready”

```text
App-ready       MOS completed its Python work.
Stage-ready     Kit made the USDZ the active USD stage.
Frame-ready     Kit rendered and presented a usable viewport frame.
Stable-ready    The scene stopped visibly filling in or changing.
Input-ready     Camera/menu input is accepted.
```

No single signal proves every one of these facts. The goal is to record enough checkpoints to identify the largest wait, without giving one weak event a misleading name.

The current experiments add one crucial distinction: a stable captured window image can still precede Kit's own stage-streaming completion by about 20 seconds. For the exact post-render streaming gate, see [MOS post-render streaming checkpoints](mos-post-render-streaming-checkpoints.md).

## Current evidence from the 2026-08-17 run

The current app logged `STAGE_OPENED` in about 0.1–1.0 seconds. Its old next-update marker followed at about 0.1–1.1 seconds. However, the same Kit log later recorded an RTX viewport/GPU-assignment message:

| Scene | `STAGE_OPENED` | RTX viewport assigned to GPU | Gap |
|---|---:|---:|---:|
| 1 | 09:49:45.981 | 09:49:52.084 | 6.1 s |
| 2 | 09:50:19.982 | 09:50:29.002 | 9.0 s |
| 3 | 09:50:57.818 | 09:51:11.847 | 14.0 s |
| 4 | 09:52:30.961 | 09:52:54.258 | 23.3 s |

This delayed RTX message is a strong diagnostic clue because it is in the same range as the participant-visible wait. It is **not** a supported promise that the scene is fully visible, so it must be treated as a correlation point, not a final readiness definition.

The log also reports `rtx.scenedb` acceleration-structure creation around scene opening. That is useful supporting evidence for renderer work, but the existing message is a start message rather than a confirmed completion event.

## Native Kit renderer events

Kit provides window-based renderer events. In Python, the supported Events 2.0 route uses `omni.kit.renderer.bind.RendererEventType` and `carb.eventdispatcher`; the old event-stream form is deprecated.

| Event | Plain meaning | Can it prove the scene is on screen? |
|---|---|---|
| `PRE_BEGIN_FRAME` | Kit is about to start rendering a frame. | No. The frame may be skipped, frozen, or stale. |
| `PRE_BEGIN_RENDER_PASS` | Kit is about to execute a render pass. | No. Rendering has not completed. |
| `RENDER_FRAME` | Kit is inside the frame render work. | Not alone. Ignore frames where `saveDrawData=true` or `draw_frozen=true`. |
| `PRESENT_RENDER_FRAME` | The present thread is updating the viewport. | Good first viewport-path marker. |
| `POST_END_RENDER_PASS` | The render pass ended. | Good timing detail, but presentation may still follow. |
| `POST_PRESENT_FRAME_BUFFER` | The renderer reached the end of rendering/presentation for a frame. | Best native presented-frame proxy. |
| `POST_END_RENDER_FRAME` | The whole render-frame sequence has ended. | Useful boundary after presentation. |

The renderer events expose `saveDrawData` and `draw_frozen` for relevant frame events. A readiness marker must reject frames where either indicates that the frame will not be displayed normally.

Official reference: [Kit renderer event reference](https://docs.omniverse.nvidia.com/kit/docs/omni.kit.renderer.core/1.1.1/Events.html).

## Captured viewport buffer

Kit's renderer-capture interface can request a callback for the next swapchain or texture capture. The callback runs when the capture buffer is available.

That gives MOS a concrete `CAPTURED_VIEWPORT_FRAME` checkpoint:

```text
scene generation changes
  → capture the current window once as a baseline
  → wait for a valid post-present event
  → request a default-window swapchain capture
  → capture callback receives pixels
  → record CAPTURED_VIEWPORT_FRAME
```

The baseline helps us describe whether later sampled images differ from what was on screen at the start. It is diagnostic context only: an asynchronous baseline request can still arrive too late to be a guaranteed old-scene image.

This proves a rendered buffer exists. It still needs a generation guard so a callback for an old scene cannot be mistaken for the new scene.

The capture interface is best used for a small diagnostic callback, not repeated screenshot files. The render-product “capture all resources” API is documented as not well supported and should not be our first choice.

Official reference: [Kit renderer capture API](https://docs.omniverse.nvidia.com/kit/docs/omni.kit.renderer.capture/latest/index.html).

## Detecting a visually settled scene

A first presented frame can be real but incomplete: textures, 3DGS data, geometry, or shaders may continue to arrive. If that happens, add `RENDER_STABLE` rather than pretending the first frame is final.

A practical diagnostic rule is:

1. Capture a small viewport buffer after the first present.
2. Capture a few later buffers at a fixed short interval.
3. Compare their luminance or pixel difference.
4. Call the scene stable only after several consecutive differences stay below a chosen threshold.

This is an approximation. The current MOS diagnostic takes four swapchain samples fifteen Kit updates apart and calls `RENDER_STABLE` after two consecutive mean byte differences are at most 3/255. A moving camera, animation, exposure change, or UI overlay also changes pixels; conversely, an old static frame can look stable. It is therefore a useful clue, not a scene-correctness proof, and works best in controlled runs with the camera held still.

## Current measured ordering

In the repaired capture run, `CAPTURED_VIEWPORT_FRAME` appeared at 2.1–7.5 s and `RENDER_STABLE` at 2.4–7.8 s. The viewer's “stage has loaded” completion message appeared 19.8–20.1 seconds later, and the participant pressed `W` another 0.35–0.51 s after that. This proves that swapchain stability is not a usable-scene definition for this application.

The viewer completion implementation waits for `ASSETS_LOADED`, then waits for `omni.streamingstatus:streaming_status` to report `isBusy=false`, plus two Kit updates. Instrument those edges next; they are the first supported application-level checkpoints that match the remaining visible delay.

## GPU, resource, and renderer profiling

The frame markers say *when* the visible delay occurs. Profiling tells us *what used the time*.

| Signal | What it can reveal | Best tool |
|---|---|---|
| GPU frame duration | Whether the GPU is busy rendering. | Kit GPU Profiler. |
| GPU memory/residency | Whether scene resources are being allocated/uploaded. | Kit Profiler or `nvidia-smi` sampling. |
| GPU copy/compute/graphics queues | Upload versus rendering versus shader work. | Tracy GPU context or Nsight Systems. |
| CPU task timeline | USD loading, Python work, background tasks, and renderer scheduling. | Kit Chrome trace / Tracy. |
| Shader/pipeline work | Compilation or pipeline creation stalls. | Tracy or Nsight; not normal MOS logs. |
| SceneDB activity | RTX scene acceleration-structure work. | Log correlation plus GPU trace. |
| Asset streaming | Late texture/geometry/3DGS data arrival. | Extension-specific stats if available; otherwise GPU trace and frame-stability results. |

Kit's profiler can record CPU and GPU timing, and its Tracy integration can include GPU context data. Use it for a controlled run after the lightweight lifecycle markers locate the slow interval.

Official references: [Kit profiling guide](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/profiling.html) and [Tracy profiler extension](https://docs.omniverse.nvidia.com/extensions/latest/ext_profiler_tracy.html).

## Recommended measurement contract

For each scene generation, record these events exactly once:

```text
FIRST_POST_LOAD_UPDATE
FIRST_RENDER_COMMAND
FIRST_DISPLAYABLE_RENDER_FRAME
FIRST_PRESENT_TO_VIEWPORT
POST_PRESENT_FRAME_BUFFER
CAPTURED_VIEWPORT_FRAME
RENDER_STABLE                 optional benchmark-only event
FIRST_USER_ACTION             first received key press, mouse-button press, or scroll
```

`FIRST_USER_ACTION` is recorded only while MOS navigation is active and once per scene generation. It is not consumed, so camera and menu controls continue normally. It is a practical participant-facing upper bound, not the instant the first pixel became visible.

For each record, include the scene generation, filename, elapsed milliseconds from `BEGIN`, and a `signal=` field naming the API or method that produced it. Ignore events from stale generations.

The routine MOS report should call `POST_PRESENT_FRAME_BUFFER + CAPTURED_VIEWPORT_FRAME` **renderer-ready**. It should call `RENDER_STABLE` **settled** only when the controlled visual-stability check is enabled and passes. It should never call an app update event “rendered” or “ready for interaction.”
