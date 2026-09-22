# Does the E3DQA Scene Viewer default NVRTC cache affect MOS or camera data?

## Question

Can `nycu.e3dqa_scene_viewer.kit` use the NVRTC cache by default, including
the camera safeguards for unusual Matrix-3D scenes, without changing MOS or
the source data?

## Answer

Yes. The two active apps now use separate cache policies:

- MOS keeps `/mnt/gen5_SSD/pierce/mos-nvrtc-cache-v2/` and its existing
  content digest for `mos_scenes.json`.
- E3DQA Scene Viewer uses
  `/mnt/gen5_SSD/pierce/e3dqa-scene-viewer-nvrtc-cache-v2/` and the stable
  scope `e3dqa-scene-viewer-v1`.

Both caches are additionally keyed by the renderer/program identity. The
viewer scope intentionally does not depend on a MOS scene list because the
viewer selects USDZ files interactively from a folder. A changed renderer or
program identity therefore produces a new artifact instead of replaying an
incompatible one. `--no-nvrtc-cache` bypasses the wrapper for either app.

The scene viewer's `usdz_folder_browser` now uses the same shared
camera-handedness check as MOS. A `cameras.json` rotation with determinant
approximately `-1` has only its camera-local X basis repaired; a proper
rotation is unchanged, and another malformed determinant is logged without a
