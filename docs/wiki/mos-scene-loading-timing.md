# Understanding MOS Scene Loading Times

## The simple version

When you press **Next** in the MOS app, the app replaces the old 3D scene with a new USDZ scene. That is a chain of jobs, not one operation. We timestamp the chain so we can answer one question:

> Which part is actually slow?

The important lesson is that “the app is ready” and “the participant can see the new scene” are different things. The old ~200 ms record only showed that MOS had finished its own setup. It did not show that Kit had rendered the new scene.

## The journey of one scene

```text
User presses Next
        ↓
BEGIN                       Start timing the scene change
        ↓
STAGE_OPENED                The USDZ becomes Kit's active scene
        ↓
ORIENTATION_DONE            Correct axes/orientation if needed
        ↓
CAMERA_READY / NAV_READY    Set camera and restore navigation
        ↓
FIRST_POST_LOAD_UPDATE      MOS setup has returned to the Kit event loop
        ↓
FIRST_RENDER_COMMAND        Kit begins a renderer frame for the window
        ↓
FIRST_PRESENT_TO_VIEWPORT   The renderer updates the viewport
        ↓
POST_PRESENT_FRAME_BUFFER   That frame reaches the end of the presentation path
        ↓
CAPTURED_VIEWPORT_FRAME     A swapchain-capture callback receives viewport pixels
        ↓
RENDER_STABLE               Several sampled images stop changing
        ↓
STREAMING_BUSY → IDLE       Kit finishes its remaining stage-streaming work
        ↓
VIEWER_STAGE_LOADED         The viewer announces all dependencies are complete
        ↓
FIRST_USER_ACTION           The first deliberate camera/menu input MOS receives
```

The first three renderer checkpoints are the useful new layer. They distinguish “MOS asked Kit to render” from “Kit actually presented a frame.” They are explained in detail in [MOS renderer readiness signals](mos-renderer-readiness-signals.md).

## Why the earlier 200 ms number was wrong for the GUI

The first three recorded scenes reached `STAGE_OPENED` in 173–228 ms, and the app-side camera/UI work took only a few more milliseconds. Those are real measurements, but they do **not** explain the 20–30 second GUI delay.

The old `FIRST_RENDER_FRAME` and `READY_FOR_INTERACTION` labels were inaccurate. Both were emitted from the next **Kit update event** after setup. An update event only says that the app loop continued. It does not say that the renderer has produced a useful new frame.

Kit may still be loading 3D Gaussian Splat data, building GPU structures, compiling shaders, or preparing the viewport after the stage opens. The app update stream continues during that work, which is why it can fire around 200 ms while the participant is still waiting.

Read those old markers as:

```text
FIRST_POST_LOAD_UPDATE = MOS's Python-side setup returned and Kit ran another update.
```

They must not be treated as visual readiness.

## The practical renderer-ready definition

We will not claim that a single generic event means “every byte is loaded and every pixel is perfect.” Instead, we will record a clear ladder:

- `FIRST_RENDER_COMMAND`: rendering has started, but the frame might not be displayable.
- `FIRST_DISPLAYABLE_RENDER_FRAME`: a normal, non-frozen frame is being rendered.
- `FIRST_PRESENT_TO_VIEWPORT`: the renderer is updating the viewport.
- `POST_PRESENT_FRAME_BUFFER`: the presentation path has completed for that frame.
- `CAPTURED_VIEWPORT_FRAME`: a callback confirms that a viewport buffer exists.
- `RENDER_STABLE`: optional stricter marker if later frames visibly refine or stream in.

For normal MOS timing, the best automatic **renderer-ready** proxy is a `POST_PRESENT_FRAME_BUFFER` event followed by `CAPTURED_VIEWPORT_FRAME`. `RENDER_STABLE` samples four later swapchain images, fifteen Kit updates apart, and fires after two consecutive image differences are tiny. It is deliberately an estimate: a stable old frame can also look stable, so it must never be called proof that the correct new scene is visible.

`FIRST_USER_ACTION` is the participant-facing reference marker. MOS records it once per scene when it receives a key press, mouse-button press, or scroll while navigation is active. It neither consumes nor delays the input. It is still an upper bound—the user may wait before acting—but it proves that MOS had reached its navigable state and received a deliberate interaction.

## The newly isolated 20-second gap

The second capture experiment changed the diagnosis. `RENDER_STABLE` is not final scene readiness: it arrived at 2.4–7.8 s, while the viewer’s “stage has loaded” message arrived at 22.7–28.0 s and the participant’s first movement followed about 0.3–0.5 s later.

The viewer code waits for Kit’s stage-streaming status to become idle after `ASSETS_LOADED`, then waits two updates before declaring success. So the next bottleneck to split is:

```text
RENDER_STABLE
  ↓
USD_ASSETS_LOADED
  ↓
STREAMING_BUSY
  ↓
STREAMING_IDLE
  ↓
two Kit updates
  ↓
VIEWER_STAGE_LOADED
```

Read [MOS post-render streaming checkpoints](mos-post-render-streaming-checkpoints.md) for the exact signals, their meanings, and the optimization map.

## Zooming in: what happens before `STAGE_OPENED`

`BEGIN → STAGE_OPENED` currently hides several jobs:

```text
BEGIN
  ↓
Close the old scene
  ↓
Create/reset an empty scene
  ↓
Ask Python to clean up unused objects
  ↓
Ask Kit to open the new USDZ
  ↓
Kit reads, unpacks, and prepares the USDZ scene
  ↓
STAGE_OPENED
```

The next timestamps will split that work into `UNLOAD_BEGIN`, `CLOSE_STAGE_DONE`, `EMPTY_STAGE_DONE`, `GC_DONE`, `OPEN_REQUESTED`, and `OPEN_CALL_RETURNED`. This lets us separate old-scene cleanup from new-file access.

## Checkpoints we can track and optimize

| Checkpoint | What it isolates | If it is slow, investigate |
|---|---|---|
| `UNLOAD_BEGIN → CLOSE_STAGE_DONE` | Releasing the old scene. | Retained resources and unnecessary teardown. |
| `CLOSE_STAGE_DONE → EMPTY_STAGE_DONE` | Resetting the temporary stage. | Redundant stage-reset work. |
| `EMPTY_STAGE_DONE → GC_DONE` | Forced Python cleanup. | Whether explicit garbage collection is pausing the app. |
| `GC_DONE → OPEN_REQUESTED` | MOS bookkeeping. | App code, only if it is measurably large. |
| `OPEN_REQUESTED → OPEN_CALL_RETURNED` | Handing the request to Kit. | Blocking calls; normally small. |
| `OPEN_CALL_RETURNED → STAGE_OPENED` | NAS/SSD access, USDZ unpacking, USD composition, and population. | Storage, file contents, references, preloading. |
| `STAGE_OPENED → NAV_READY` | Orientation, camera, and navigation setup. | Metadata and repeated stage edits. |
| `NAV_READY → FIRST_POST_LOAD_UPDATE` | Return to Kit's event loop. | App-side deferred work. |
| `FIRST_POST_LOAD_UPDATE → FIRST_PRESENT_TO_VIEWPORT` | Getting actual rendering started and routed to the viewport. | GPU assignment, renderer/Hydra startup, resource upload. |
| `FIRST_PRESENT_TO_VIEWPORT → CAPTURED_VIEWPORT_FRAME` | Producing an accessible rendered buffer. | Renderer/presentation backlog. |
| `CAPTURED_VIEWPORT_FRAME → RENDER_STABLE` | The captured window image stops changing. | Useful diagnostic, but may still be a stable incomplete/stale image. |
| `RENDER_STABLE → STREAMING_IDLE` | Kit's remaining stage streaming. | Asset-streaming state, GPU uploads/residency, 3DGS/geometry, texture work, and storage. |
| `STREAMING_IDLE → VIEWER_STAGE_LOADED` | Viewer completion policy. | The two mandated updates; only investigate if unexpectedly large. |

## How we will use the results

For each scene transition, we will compare first-launch and later scene changes, NAS versus local SSD, and different USDZ variants. We improve the biggest repeatable gap first:

- A large pre-`STAGE_OPENED` gap points to cleanup, storage, or USD loading.
- A large `STAGE_OPENED → FIRST_PRESENT_TO_VIEWPORT` gap points to renderer/GPU setup.
- A large `CAPTURED_VIEWPORT_FRAME → RENDER_STABLE` gap points to late resource streaming or visual refinement.
