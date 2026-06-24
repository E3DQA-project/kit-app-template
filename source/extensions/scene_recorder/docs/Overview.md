# Overview

The Scene Recorder extension adds a dockable panel with two sections:

1. **Record Camera Path** — captures the active viewport camera pose each frame while you navigate, then saves the trajectory to JSON and optionally bakes+exports as video.
2. **Replay Trajectory** — loads a saved JSON, bakes it as an animated USD camera in the current stage, sets the timeline, and optionally exports the replay as video via `omni.kit.window.movie_capture`.
