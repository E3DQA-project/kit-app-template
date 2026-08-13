# MOS Scene Readiness Logging Design

## Goal

Make MOS scene loading diagnosable from the terminal while a participant uses the GUI. For each ordered USDZ scene, the log should show progress from the initial disk load through stage setup, camera activation, navigation setup, and the first render/update tick after setup.

## Readiness contract

The extension will emit a final `READY_FOR_INTERACTION` record only after:

- the requested USDZ stage has opened;
- scene orientation setup has completed or reported a failure;
- the configured camera has been initialized and activated, or a clear camera fallback is reported;
- WASD/mouse and controller navigation settings have been applied;
- a deferred post-load callback has run after the setup work, serving as the practical Kit-side signal that the viewport can begin displaying the configured scene.

The log will explicitly identify fallback or failed camera/render signals rather than claiming a stronger guarantee than the available Kit APIs provide.

## Log sequence

Each scene will use a consistent `[MOS_LOAD]` prefix and include the scene index, filename, and elapsed milliseconds where available:

`BEGIN` → `STAGE_OPENED` → `ORIENTATION_DONE` → `CAMERA_READY` or `CAMERA_FALLBACK` → `NAV_READY` → `FIRST_RENDER_FRAME` → `READY_FOR_INTERACTION`.

Existing scene-loading behavior and state transitions remain unchanged except for the additional diagnostic state needed to correlate callbacks with the active scene.

## Implementation boundary

Instrumentation belongs in `nycu.mos_app_extension` because that extension owns ordered scene loading, post-load camera setup, and navigation defaults. No generated artifacts, application wiring, score files, or legacy applications will be changed.

## Verification

- Add narrow unit coverage for the diagnostic timing/recording helper without requiring Kit or a GPU.
- Run the narrow MOS Python unit tests and static syntax validation.
- Start the MOS app in the existing `mos_app` tmux session and capture the emitted lifecycle records during a scene load when practical.
