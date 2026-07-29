# Application instructions

Only these applications are in active development:

- `nycu.e3dqa_scene_viewer.kit`: E3DQA viewer and QA tooling.
- `nycu.mos_app.kit`: MOS sequential scene evaluation app.

The other `.kit` files in this directory (`my_editor.kit`, `my_editor_1.kit`, `my_editor_1_streaming.kit`, and `my_editor_clean.kit`) are legacy examples. Leave them unchanged and do not use them for new implementation or verification unless explicitly requested.

Before changing an app, inspect its dependencies, settings, test block, and the extensions it loads. Keep app-level changes limited to composition, settings, and dependency wiring; put application behavior in an extension.

The generated dependency lock section at the bottom of each `.kit` file is not hand-maintained. Regenerate it with the repo tooling after dependency changes.
