# Why does the DualShock 4 right stick jitter or appear to reverse in E3DQA Scene Viewer?

**Question:** In `nycu.e3dqa_scene_viewer`, why can the DS4 right stick (camera look) jitter or appear to move the camera in the opposite direction, and is the controller faulty?

**Answer:** The active app delegates DS4 input to Kit's `omni.kit.manipulator.camera`; it has no E3DQA-specific gamepad event handler. The installed Kit default maps the right stick to `look` with a `0.10` dead-zone and `0.75` scale. Therefore a worn stick, wireless/remote-input reconnect, or input values just above `0.10` can produce genuine jitter, but the current software configuration also contains a verified directional issue:

- `camera_controls` starts with the E3DQA viewer and writes `/persistent/exts/omni.kit.manipulator.camera/lookSpeed/0 = -180.0` on every startup (and when its preset is reapplied).
- Kit applies `lookSpeed` to gamepad look as well as mouse look, so the horizontal right-stick axis is deliberately inverted.
- This inversion was added to compensate for Matrix-3D's camera-image convention and the 180-degree local roll applied to the initial `/BrowserCamera` pose. It is a global input-axis change, not a DS4 calibration.

As a result, a consistent horizontal reversal is software-caused. Apparent direction changes at different orientations are also plausible because look is evaluated in the camera's rolled local frame. A raw DS4 axis trace is still required to attribute jitter specifically to hardware: if the untouched right-stick values remain nonzero or change sign outside the configured dead-zone, the controller/connection is contributing; otherwise the camera mapping is responsible.

**Recommended remediation:** Separate dataset camera-pose correction from interactive look input: restore a positive horizontal `lookSpeed`, retain the initial camera's local roll correction, and raise the Kit `gamePad.look.deadZone` (for example, to `0.18`–`0.25`) only if an input trace shows drift. Validate with the physical DS4 by holding the right stick centered, then moving it horizontally at a level initial camera pose and after a rotated view.

**Verified against:** live `kit-app-template` tmux session launched as `nycu.e3dqa_scene_viewer.kit` on 2026-09-23; `source/extensions/camera_controls/camera_controls/extension.py`; the active persisted `user.config.json`; and Kit SDK `omni.kit.manipulator.camera-110.1.0+698af100` source/configuration.
