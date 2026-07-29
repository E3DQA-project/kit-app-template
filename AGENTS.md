# Codex project instructions

## Scope and priorities

This repository is an NVIDIA Omniverse Kit application template customized for two active applications:

- `source/apps/nycu.e3dqa_scene_viewer.kit` — the E3DQA scene viewer, with USDZ browsing, metric scoring, camera controls, and scene recording.
- `source/apps/nycu.mos_app.kit` — the MOS evaluation app, with participant identification, ordered USDZ scene evaluation, scoring, and score persistence.

Treat every other application under `source/apps/` as legacy. Do not add features to, launch, test, or use a legacy app as a reference unless the task explicitly names it. The `templates/` directory is the upstream Kit template material and should only be changed when the task is explicitly about templates.

## Repository map

- `source/apps/`: Kit application definitions. The two `nycu.*.kit` files are the active entry points.
- `source/extensions/`: project extensions. The E3DQA app uses `usdz_folder_browser`, `metric_sliders`, `camera_controls`, and `scene_recorder`; the MOS app uses `nycu.mos_app_extension` and `nycu.my_usd_viewer_setup_extension`.
- `source/data/mos_scenes.json`: MOS scene catalog. `source/data/scores/` contains local evaluation output and is user data; preserve it unless the task explicitly concerns scores.
- `premake5.lua`: authoritative list of applications and explicitly linked project extensions for the build graph.
- `repo.toml`: Kit/repo build, precache, packaging, and launch configuration. Its precache list may contain stale legacy entries; do not treat that list as the active-app list.
- `_build/`, `source/extscache/`, `_repo/`, and generated/version-lock sections are generated or cached artifacts. Do not hand-edit them.

## Development rules

1. Read the relevant `.kit`, extension `config/extension.toml`, and implementation/docs before changing behavior.
2. Keep application wiring in the `.kit` file and extension behavior in the owning extension. Avoid duplicating settings across the two active apps.
3. Preserve Kit/TOML ordering and generated version-lock blocks. If dependencies change, regenerate them through the repository tooling rather than manually editing the generated block.
4. For MOS changes, preserve ordered scene loading, participant-scoped score persistence, and the `${app}/../data/mos_scenes.json` override unless the task changes that contract.
5. For E3DQA changes, account for viewport/camera state and GPU/VRAM-sensitive stage loading, unloading, recording, and capture behavior.
6. Do not delete or rewrite existing uncommitted user data. In particular, preserve changes under `source/data/`.

## Verification

Use the repository entry point from the repo root:

```bash
./repo.sh build
./repo.sh launch nycu.e3dqa_scene_viewer.kit
./repo.sh launch nycu.mos_app.kit
./repo.sh test
```

When a full Kit run is impractical, run the narrowest available test or static/TOML validation and report what was and was not exercised. Prefer headless/no-window flags for smoke tests where supported.
