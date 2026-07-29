# Extension instructions

Active extension ownership:

- E3DQA Scene Viewer: `usdz_folder_browser`, `metric_sliders`, `camera_controls`, `scene_recorder`.
- MOS App: `nycu.mos_app_extension` and `nycu.my_usd_viewer_setup_extension`.

Keep UI and runtime behavior in the owning extension rather than embedding Python behavior in an app `.kit` file. Update `config/extension.toml` dependencies when imports introduce a required Kit extension. Preserve optional dependencies when the code already supports minimal configurations.

For MOS work, treat `source/data/mos_scenes.json` and participant score files as part of the app contract. For E3DQA work, test scene transitions and camera/viewport behavior where relevant. `sample_extension` and the `nycu.my_usd_viewer_messaging_extension` are not active app dependencies; treat them as legacy unless a task explicitly names them.

Do not edit `__pycache__`, `_build`, or `source/extscache` artifacts. Keep extension docs and tests aligned with behavior changes.
