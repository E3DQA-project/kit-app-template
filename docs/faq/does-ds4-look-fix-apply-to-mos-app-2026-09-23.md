# Does the DS4 right-stick fix apply to MOS App?

**Question:** The E3DQA Scene Viewer right-stick full-deflection fix works. Why does MOS App still jitter or stop, and does it need the same fix?

**Answer:** The first implementation lived in E3DQA's `camera_controls` extension. `nycu.mos_app.kit` does not load that extension. MOS uses its own `nycu.mos_app_extension` for camera presets, while both apps use the same Kit 110.1.0 `omni.kit.manipulator.camera` gamepad handler. MOS also writes horizontal `lookSpeed/0` as a negative value, so the Kit retained-value scaling defect can produce the same full-stick behavior.

The correction has been moved into the UI-free `nycu.gamepad_look_fix` extension. Both `camera_controls` and `nycu.mos_app_extension` now depend on it. It restores Kit's retained look values to their unscaled form before the next gamepad event is applied. This preserves each app's camera direction and sensitivity. Three focused tests cover horizontal sign reversal, vertical decay, and unrelated actions. The release build succeeded, the MOS app log confirms installation, and the user verified that full left, right, up, and down deflection all work normally in MOS.
