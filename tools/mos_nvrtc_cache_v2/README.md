# Single-scene NVRTC PTX + name cache experiment

This is an opt-in experiment, not a change to normal MOS launch. It addresses
the missing `nvrtcGetLoweredName` result in the earlier PTX-only replay.

From the repository root, in conda `pierce_base` and tmux `mos_app`:

```sh
python3 tools/mos_nvrtc_cache_v2/run_experiment.py --mode seed --scene /absolute/path/scene.usdz
python3 tools/mos_nvrtc_cache_v2/run_experiment.py --mode replay --scene /absolute/path/scene.usdz
```

Complete and inspect the seed run before replay. Both commands restrict the
scene list to the specified scene. They build the shim, hash the scene before
launch, and generate distinct directories under
`_mos_asset_loading_experiment/nvrtc-cache-v2/` plus records in `docs/records/`.
Hashing warms filesystem caches; these runs evaluate compilation reuse and
are not cold-disk benchmarks. `--prepare-only` validates/builds without a GUI.

The artifact is a versioned, length-delimited binary containing its key, PTX,
and every requested expression/name pair, protected by SHA-256. Incomplete or
corrupt artifacts fall back to original compilation before reporting success.
Returned names are owned by the program state until destruction. Input keys
include source, filename, copied headers, options, ordered name expressions,
renderer SHA-256, and the launcher-provided scene SHA-256 scope.

**Private API limitation:** MOS uses `__nvrtcCPEx`. Its extra inputs are not
fully understood. The prototype forwards all three extra arguments unchanged,
but fingerprints only the scalar first extra argument. Headers are copied as
C strings; that is not a verified complete representation for private packed
inputs. The launcher explicitly enables `MOS_V2_PRIVATE_EXPERIMENT=1` for this
bounded experiment. A successful single-scene run does not validate a general
persistent cache. Do not enable this globally or mix renderer versions/settings
between the paired runs. Normal launch has no preload.

The fixture uses real embedded NVRTC through public creation calls. Run it
with `MOS_TEST_PRELOAD=1` to resolve calls from the actual preload namespace:

```sh
MOS_TEST_PRELOAD=1 python3 tools/mos_nvrtc_cache_v2/test_integration.py \
  _mos_asset_loading_experiment/nvrtc-cache-v2/build/libmos_nvrtc_cache_v2.so \
  _build/linux-x86_64/release/extscache/omni.hydra.rtx-1.0.4+698af100.lx64.r/bin/deps/libnrend.so
```

It checks two program states, cold/warm output identity, skipped compile,
name-pointer lifetime, unknown-name failure, truncation/corruption fallback,
and expression-list key isolation. It does not test GPU module execution or
private CPEx input semantics. The current build uses the existing SHA-256
implementation in `tools/mos_nvrtc_cache/src/key.cpp` and its header.

Success requires observed `tracked private=1`, `stored names=5` on seed,
`hit` plus all five `name_hit` on replay, no original long compile on replay,
and the user confirming a visible and traversable scene. `RENDER_STABLE` alone
can describe a black viewport. Keep the process open until the user closes it.
