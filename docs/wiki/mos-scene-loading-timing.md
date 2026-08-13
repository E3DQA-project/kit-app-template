# Understanding MOS Scene Loading Times

## The simple version

When you press **Next** in the MOS app, the app needs to replace the old 3D scene with a new USDZ scene. That is not one single operation. It is a chain of smaller steps.

We want a timestamp at each step so we can answer one important question:

> Which part is actually slow?

Without those timestamps, a long wait only tells us that *something* was slow. It does not tell us whether the delay came from reading the file, opening the USD stage, positioning the camera, or getting the renderer ready.

## The journey of one scene

```text
User presses Next
        ↓
BEGIN                  Start timing the scene change
        ↓
STAGE_OPENED           The requested USDZ becomes the active Kit scene
        ↓
ORIENTATION_DONE       Correct the scene's axes/orientation if needed
        ↓
CAMERA_READY           Find cameras.json, place the camera, activate it
        ↓
NAV_READY              Restore navigation and interaction state
        ↓
FIRST_RENDER_FRAME     Kit reaches the first update after setup
        ↓
READY_FOR_INTERACTION  The app considers the scene usable
```

Each line will include elapsed time in milliseconds from `BEGIN`. For example:

```text
[MOS_LOAD] event=BEGIN                 elapsed_ms=0
[MOS_LOAD] event=STAGE_OPENED          elapsed_ms=950
[MOS_LOAD] event=ORIENTATION_DONE      elapsed_ms=970
[MOS_LOAD] event=CAMERA_READY          elapsed_ms=1010
[MOS_LOAD] event=NAV_READY             elapsed_ms=1020
[MOS_LOAD] event=FIRST_RENDER_FRAME    elapsed_ms=1040
[MOS_LOAD] event=READY_FOR_INTERACTION elapsed_ms=1040
```

This example says that almost all of the delay—950 of 1,040 ms—happened before the USDZ stage opened. That would direct us to investigate file access, USD parsing, asset population, or memory pressure before touching camera or UI code.

## What the app measures today

Today, the MOS app logs a coarse start message such as `Loading 2/7`, then later logs a ready-status message after scene setup.

That gives us one rough total duration, but no breakdown. The current code also contains a helper that can create `[MOS_LOAD]` timestamp lines, but the main scene-loading code does not call it yet.

So the current logs cannot tell us which lifecycle step is the bottleneck.

## What each future timestamp means

| Timestamp | Plain meaning | What a large delay before it suggests |
|---|---|---|
| `BEGIN` | We started replacing the scene. | This is always zero—the reference point. |
| `STAGE_OPENED` | Kit opened the requested USDZ as the current scene. | Disk/network access, USDZ reading, USD parsing, scene population, or cleanup of the previous scene. |
| `ORIENTATION_DONE` | Coordinate correction finished. | Orientation code or USD stage edits. Usually expected to be small. |
| `CAMERA_READY` | The camera was found/created and activated. | Finding or reading `cameras.json`, or camera/viewport setup. |
| `CAMERA_FALLBACK` | Camera metadata was missing or setup failed, so the app continued without it. | This is an explanation of a fallback, not a successful camera measurement. |
| `NAV_READY` | Controls and app state are ready for the participant. | Navigation-setting or UI work. Usually expected to be small. |
| `FIRST_RENDER_FRAME` | Kit completed the first safe update after scene setup. | Renderer scheduling, shader/resource work, or work deferred until after stage opening. |
| `READY_FOR_INTERACTION` | The app's practical “you may start using it” marker. | Any remaining app-side scheduling after the first update. |

## Important limitation

`READY_FOR_INTERACTION` will mean that the application has finished its measured setup and reached a practical Kit update point. It does **not** prove the exact instant that every pixel reached the physical monitor.

Measuring exact GPU completion or display scanout needs deeper GPU/display profiling. We will not pretend the normal app logs provide that. They are still enough to identify most app-side and scene-loading bottlenecks.

## How we will use the results

For each scene transition, we will keep the timestamps from the `mos_app` tmux session and calculate the gap between each pair of events.

We will compare:

- The first scene after launching the app, which may pay one-time startup or shader costs.
- Later scene changes, which show normal scene-to-scene overhead.
- Different USDZ variants and their storage location, such as NAS versus local SSD.

Then we will improve only the biggest repeatable delay first. For example, if `BEGIN → STAGE_OPENED` is slow, we investigate scene/file loading—not camera code.
