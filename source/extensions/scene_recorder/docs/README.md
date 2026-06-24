# Scene Recorder

Record live WASD camera navigation as a trajectory JSON and optionally export video. Replay any saved trajectory in another scene with video export.

## Features

- **Record**: Start/stop recording the active viewport camera pose at a configurable sample rate. Saves position, rotation (Euler + quaternion), and full 4x4 world-space transform matrix per frame.
- **Save JSON**: Export the recorded trajectory to a JSON file for later use.
- **Bake & Export Video**: Bake the trajectory as USD time-sampled camera animation and trigger `omni.kit.window.movie_capture` to render it to video.
- **Replay**: Load any previously saved trajectory JSON, bake it into the current scene as an animated USD camera, and set the viewport timeline. Export as video with movie capture.
