# Default MOS NVRTC cache

## Goal

Make the tested MOS NVRTC PTX + lowered-name cache the default for MOS launches, while keeping all other Kit apps unchanged. A cache miss, invalid artifact, or incompatible identity must run the original NVRTC compiler and save a new artifact; it must never prevent MOS from starting.

## Scope and cache location

- Intercept only `./repo.sh launch nycu.mos_app.kit ...`.
- Do not change normal launch behavior for `nycu.e3dqa_scene_viewer.kit` or legacy apps.
- Persist artifacts below `/mnt/gen5_SSD/pierce/mos-nvrtc-cache-v2` (local SSD, outside the repository, user-accessible, not Git-tracked).
- Preserve an explicit `--no-nvrtc-cache` launcher opt-out for diagnosing an unexpected result.

## Launch flow

1. `repo.sh` recognizes a MOS launch unless `--no-nvrtc-cache` is present.
2. A dedicated wrapper builds or reuses the preload shim, resolves the renderer library, identifies the selected scene-list setting (or MOS default list), and derives a stable scope digest from that list's bytes.
3. It starts the existing repo launch command with `LD_PRELOAD`, the renderer identity, the SSD cache directory, and `MOS_V2_MODE=auto`.
4. In `auto`, the shim computes its existing identity key. A valid matching artifact replays PTX and all lowered names. Any miss or failed validation invokes original NVRTC, retrieves PTX/names, and atomically stores an artifact.
5. `--no-nvrtc-cache` removes only the wrapper's cache environment and forwards the normal MOS launch command.

The key continues to include renderer SHA-256, generated source, copied headers, compiler options and ordered name expressions. The launcher scope differentiates scene-list selections. The cache is not shared across renderer versions.

## Safety and limitations

`__nvrtcCPEx` has opaque private arguments. The current prototype forwards all arguments and fingerprints the known scalar but does not prove complete identity coverage. This implementation therefore retains cache validation and automatic compile fallback, emits clear `MOS_V2` hit/miss/store diagnostics, and keeps the opt-out. It is a default operational cache for the verified MOS setup, not a general renderer cache API.

No cache files are deleted by this change. Existing experimental artifacts under the repository remain untouched. The new SSD directory is created on first MOS cache launch only.

## Tests and acceptance criteria

1. Add launcher-focused tests covering MOS detection, non-MOS pass-through, `--no-nvrtc-cache`, cache-directory environment, and scene-list scope derivation.
2. Preserve the real-NVRTC preload integration test: output identity, skipped compile, five-name lifetime, corruption fallback and name-list isolation.
3. Run the camera convention test unchanged after integration.
4. Manually run a seed/default MOS launch and a second default MOS launch of the same scene. The second run must show one cache hit, five name hits, no original compile event, a visible movable scene, and normal exit.
5. Run the same command with `--no-nvrtc-cache`; it must launch without the preload environment.

## Rollback

`--no-nvrtc-cache` is immediate operational rollback. Git rollback is a normal revert of the default-launch commit; artifacts under `/mnt/gen5_SSD/pierce/mos-nvrtc-cache-v2` are left intact and harmless without the preload launcher.
