# Default MOS NVRTC Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PTX plus lowered-name caching automatic for local `nycu.mos_app.kit` launches, with compile-on-miss fallback and a `--no-nvrtc-cache` escape hatch.

**Architecture:** `tools/repoman/launch.py` remains the authority for app selection. When it selects MOS, it starts a focused Python launcher that computes a scene-list scope, builds/reuses the preload shim, and passes a sanitized environment to the built MOS app. The shim gains `auto` mode: replay valid artifacts, otherwise forward NVRTC and atomically persist the result. Other Kit apps retain the exact direct process launch path.

**Tech Stack:** Python 3 standard library (`argparse`, `hashlib`, `subprocess`, `unittest`), Bash entrypoint through repoman, C++17 LD_PRELOAD interposer, embedded NVRTC, existing SHA-256 helper.

**Spec:** `docs/superpowers/specs/2026-09-17-default-mos-nvrtc-cache-design.md`

## Global Constraints

- Enable only local `nycu.mos_app.kit`, never other Kit apps or container/package launches.
- Use `/mnt/gen5_SSD/pierce/mos-nvrtc-cache-v2`; do not store persistent artifacts in the repository or NAS.
- Never delete cache files; invalid/corrupt/missing artifacts compile normally.
- Keep `--no-nvrtc-cache` as an explicit launch-level opt-out.
- Preserve renderer SHA, source, headers, options, ordered expressions and scene-list scope in cache identity.
- Do not modify camera convention code or normal app scene-loading logic.
- Do not commit `.repowise/` local databases/caches.

---

## File Structure

- Modify: `tools/repoman/launch.py` — parse opt-out and route only local MOS through the cache launcher.
- Create: `tools/mos_nvrtc_cache_v2/default_launch.py` — build shim, resolve scene-list scope, prepare environment, execute MOS app.
- Create: `tools/mos_nvrtc_cache_v2/test_default_launch.py` — standard-library tests for routing helpers and environment construction.
- Modify: `tools/mos_nvrtc_cache_v2/interposer.cpp` — accept `auto` and replay valid artifacts before original compile.
- Modify: `tools/mos_nvrtc_cache_v2/test_integration.py` — assert `auto` cold stores then warm replays using the real preload namespace.
- Modify: `tools/mos_nvrtc_cache_v2/README.md` — document normal launch, cache location, opt-out, safety limits and recovery.
- Modify: `docs/faq/nvrtc-ptx-and-names.md` — replace historical experimental-only wording with default-launch behavior and limitations.
- Create: `docs/records/YYYYMMDD-...-default-cache-*.md` — produced only after each interactive GUI run; never pre-create a fake result.

### Task 1: Test and implement the default-launch helper

**Files:**
- Create: `tools/mos_nvrtc_cache_v2/default_launch.py`
- Create: `tools/mos_nvrtc_cache_v2/test_default_launch.py`

**Interfaces:**
- Produces `resolve_scene_list(root: Path, kit_args: list[str]) -> Path`.
- Produces `scope_digest(scene_list: Path) -> str` using SHA-256 of raw list bytes.
- Produces `build_environment(root: Path, cache_root: Path, scene_list: Path, shim: Path, renderer: Path, inherited: Mapping[str, str]) -> dict[str, str]`.
- Produces CLI `python3 default_launch.py --app-command /abs/path/to/nycu.mos_app.kit.sh -- <Kit args>`; it exits with the app process return code.

- [ ] **Step 1: Write failing helper tests**

```python
class DefaultLaunchTests(unittest.TestCase):
    def test_explicit_scene_list_beats_source_default(self):
        root = self.make_root(default_list='default.json')
        chosen = module.resolve_scene_list(
            root, ['--/exts/nycu.mos_app_extension/sceneListPath=/tmp/custom.json']
        )
        self.assertEqual(chosen, Path('/tmp/custom.json'))

    def test_scope_is_content_digest_not_path_digest(self):
        first = self.write('one.json', b'{"scenes":["a.usdz"]}')
        second = self.write('two.json', b'{"scenes":["a.usdz"]}')
        self.assertEqual(module.scope_digest(first), module.scope_digest(second))

    def test_environment_is_auto_mode_and_strips_inherited_preload(self):
        env = module.build_environment(root, cache_root, list_path, shim, renderer,
            {'LD_PRELOAD': '/unrelated.so', 'MOS_V2_MODE': 'replay', 'KEEP': 'yes'})
        self.assertEqual(env['MOS_V2_MODE'], 'auto')
        self.assertEqual(env['MOS_V2_DIR'], str(cache_root))
        self.assertEqual(env['LD_PRELOAD'], str(shim))
        self.assertEqual(env['KEEP'], 'yes')

    def test_missing_explicit_scene_list_is_rejected_before_launch(self):
        with self.assertRaisesRegex(ValueError, 'scene list'):
            module.resolve_scene_list(root, ['--/exts/nycu.mos_app_extension/sceneListPath=/missing.json'])
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python3 tools/mos_nvrtc_cache_v2/test_default_launch.py`

Expected: FAIL because `default_launch.py` and its public helper functions do not exist.

- [ ] **Step 3: Implement minimal helper and CLI**

```python
CACHE_ROOT = Path('/mnt/gen5_SSD/pierce/mos-nvrtc-cache-v2')

def resolve_scene_list(root, kit_args):
    prefix = '--/exts/nycu.mos_app_extension/sceneListPath='
    explicit = next((arg[len(prefix):] for arg in kit_args if arg.startswith(prefix)), None)
    candidate = Path(explicit) if explicit else root / 'source/data/mos_scenes.json'
    if not candidate.is_file():
        raise ValueError(f'scene list does not exist: {candidate}')
    return candidate.resolve()

def scope_digest(scene_list):
    return hashlib.sha256(scene_list.read_bytes()).hexdigest()
```

Build the existing interposer with `g++ -std=c++17 -shared -fPIC -Wall -Wextra -Werror`, place it under `CACHE_ROOT / 'shim' / <renderer-sha> / 'libmos_nvrtc_cache_v2.so'`, and use atomic replacement only after successful compilation. Populate `MOS_V2_LIBRARY`, `MOS_V2_DIR=CACHE_ROOT/'artifacts'/scope`, `MOS_V2_SCOPE`, `MOS_V2_MODE=auto`, `MOS_V2_PRIVATE_EXPERIMENT=1`, `LD_PRELOAD`, and `OMNI_REPO_ROOT`. Remove inherited `LD_PRELOAD` and all inherited `MOS_V2_*` values first. Execute `[app_command, *kit_args]` with `subprocess.run` and return its code.

- [ ] **Step 4: Run helper tests to verify GREEN**

Run: `python3 tools/mos_nvrtc_cache_v2/test_default_launch.py`

Expected: PASS, four tests, zero failures.

- [ ] **Step 5: Commit**

```bash
git add tools/mos_nvrtc_cache_v2/default_launch.py tools/mos_nvrtc_cache_v2/test_default_launch.py
git commit -m "feat: add default MOS cache launcher"
```

### Task 2: Make the interposer auto-cache safely

**Files:**
- Modify: `tools/mos_nvrtc_cache_v2/interposer.cpp`
- Modify: `tools/mos_nvrtc_cache_v2/test_integration.py`

**Interfaces:**
- Consumes `MOS_V2_MODE=auto` from Task 1.
- Produces `MOS_V2 event=hit` and five `name_hit` events when a valid artifact exists.
- Produces normal `compile` then `stored` events on a miss or invalid artifact.

- [ ] **Step 1: Write failing auto-mode test**

In `parent`, run two processes with `MOS_V2_MODE='auto'` before the existing seed/replay checks:

```python
env['MOS_V2_MODE'] = 'auto'
first, first_log = invoke()
second, second_log = invoke()
assert first == second
assert first_log.count('event=compile ') == 2
assert first_log.count('event=stored ') == 2
assert second_log.count('event=hit ') == 2
assert 'event=compile ' not in second_log
```

- [ ] **Step 2: Run test to verify RED**

Run: `g++ -std=c++17 -shared -fPIC -Wall -Wextra -Werror -Itools/mos_nvrtc_cache/include tools/mos_nvrtc_cache_v2/interposer.cpp tools/mos_nvrtc_cache/src/key.cpp -ldl -pthread -o /tmp/libmos_nvrtc_cache_v2.so && MOS_TEST_PRELOAD=1 python3 tools/mos_nvrtc_cache_v2/test_integration.py /tmp/libmos_nvrtc_cache_v2.so _build/linux-x86_64/release/extscache/omni.hydra.rtx-1.0.4+698af100.lx64.r/bin/deps/libnrend.so`

Expected: FAIL because `enabled()` rejects `auto` and replay is conditional on `replay` only.

- [ ] **Step 3: Implement the minimal auto behavior**

Change `enabled()` to accept `seed`, `replay`, or `auto`. In `nvrtcCompileProgram`, calculate the key once; call `read(*s)` when mode is `replay` or `auto`; return cached values only if `read` succeeds. Leave the existing original-compiler path and `persist(*s)` unchanged, so `auto` on any miss or rejection compiles and stores normally.

- [ ] **Step 4: Run preload integration test to verify GREEN**

Run the command from Step 2.

Expected: PASS, including original seed/replay, corruption fallback, name isolation and the new auto cold/warm assertions.

- [ ] **Step 5: Commit**

```bash
git add tools/mos_nvrtc_cache_v2/interposer.cpp tools/mos_nvrtc_cache_v2/test_integration.py
git commit -m "feat: enable automatic NVRTC cache fallback"
```

### Task 3: Route only local MOS launches through the cache launcher

**Files:**
- Modify: `tools/repoman/launch.py`
- Modify: `tools/mos_nvrtc_cache_v2/test_default_launch.py`

**Interfaces:**
- Consumes `--no-nvrtc-cache` at the repo-launch parser level.
- Consumes Task 1 CLI and `app_build_path` from `launch_kit`.
- Produces direct `kit_cmd` for every app except local `nycu.mos_app.kit` without opt-out.

- [ ] **Step 1: Write failing routing tests**

Import `tools/repoman/launch.py` with its Kit dependencies replaced by minimal `sys.modules` stubs. Patch `_run_process` and assert:

```python
launch.launch_kit('nycu.mos_app.kit', build_dir, {}, False, [], False)
run.assert_called_once()
assert 'tools/mos_nvrtc_cache_v2/default_launch.py' in run.call_args.args[0]

launch.launch_kit('nycu.e3dqa_scene_viewer.kit', build_dir, {}, False, [], False)
assert run.call_args.args[0][0].endswith('nycu.e3dqa_scene_viewer.kit.sh')

launch.launch_kit('nycu.mos_app.kit', build_dir, {}, False, [], True)
assert run.call_args.args[0][0].endswith('nycu.mos_app.kit.sh')
```

- [ ] **Step 2: Run routing tests to verify RED**

Run: `python3 tools/mos_nvrtc_cache_v2/test_default_launch.py`

Expected: FAIL because `launch_kit` lacks the opt-out parameter and always invokes the built app directly.

- [ ] **Step 3: Implement parser and route**

Add `--no-nvrtc-cache` as `action='store_true'` in `add_args`; pass `options.no_nvrtc_cache` through `run_repo_tool` into `launch_kit`. Extend `launch_kit` with `no_nvrtc_cache: bool = False`. After `kit_cmd` is complete, replace it only when:

```python
if app_name == 'nycu.mos_app.kit' and not no_nvrtc_cache:
    wrapper = Path(omni.repo.man.resolve_tokens('${root}/tools/mos_nvrtc_cache_v2/default_launch.py'))
    kit_cmd = [sys.executable, str(wrapper), '--app-command', *kit_cmd[:1], '--', *kit_cmd[1:]]
```

Keep `--container` and `--package` launches direct; their `launch_kit` call sites explicitly pass `no_nvrtc_cache=True`.

- [ ] **Step 4: Run routing and helper tests to verify GREEN**

Run: `python3 tools/mos_nvrtc_cache_v2/test_default_launch.py`

Expected: PASS, including non-MOS direct routing and MOS opt-out direct routing.

- [ ] **Step 5: Commit**

```bash
git add tools/repoman/launch.py tools/mos_nvrtc_cache_v2/test_default_launch.py
git commit -m "feat: enable MOS NVRTC cache by default"
```

### Task 4: Document, build, and verify the integrated launch

**Files:**
- Modify: `tools/mos_nvrtc_cache_v2/README.md`
- Modify: `docs/faq/nvrtc-ptx-and-names.md`
- Create: `docs/records/YYYYMMDD-...-default-cache-*.md` after live runs only

**Interfaces:**
- Documents `./repo.sh launch nycu.mos_app.kit` as default cache behavior.
- Documents `./repo.sh launch nycu.mos_app.kit --no-nvrtc-cache` as direct fallback.

- [ ] **Step 1: Write documentation acceptance checklist**

Add this exact checklist to the cache README:

```markdown
- [ ] First default launch: `MOS_V2 event=compile` then `stored`.
- [ ] Second identical default launch: `hit`, five `name_hit`, no `compile`.
- [ ] Scene is visible and camera is movable.
- [ ] `--no-nvrtc-cache` has no `MOS_V2` log events.
```

- [ ] **Step 2: Update docs**

State the absolute SSD path, automatic miss fallback, renderer-version invalidation, private-CPEx limitation, and no-cache recovery command. Do not claim every scene/configuration is proven until live results exist.

- [ ] **Step 3: Run automated verification**

Run:

```bash
python3 tools/mos_nvrtc_cache_v2/test_default_launch.py
g++ -std=c++17 -shared -fPIC -Wall -Wextra -Werror -Itools/mos_nvrtc_cache/include tools/mos_nvrtc_cache_v2/interposer.cpp tools/mos_nvrtc_cache/src/key.cpp -ldl -pthread -o /tmp/libmos_nvrtc_cache_v2.so
MOS_TEST_PRELOAD=1 python3 tools/mos_nvrtc_cache_v2/test_integration.py /tmp/libmos_nvrtc_cache_v2.so _build/linux-x86_64/release/extscache/omni.hydra.rtx-1.0.4+698af100.lx64.r/bin/deps/libnrend.so
PYTHONPATH=source/extensions/nycu.camera_conventions python3 source/extensions/nycu.camera_conventions/tests/test_conventions.py
git diff --check
```

Expected: all tests pass; two camera convention tests pass; no whitespace errors.

- [ ] **Step 4: Run interactive cold/warm/opt-out tests**

Use `mos_app` tmux after `conda activate pierce_base`. Launch the same MOS scene list three times: initial default launch, repeated default launch, and `--no-nvrtc-cache`. Wait for user interaction and normal app closure each time. Write timestamp records under `docs/records/` only after each app exits.

Expected: default warm run has no original NVRTC compile and a visible movable scene; opt-out has no `MOS_V2` events and retains camera behavior.

- [ ] **Step 5: Commit and push**

```bash
git add tools/mos_nvrtc_cache_v2/README.md docs/faq/nvrtc-ptx-and-names.md docs/records
git commit -m "docs: document default MOS NVRTC cache"
git push origin cleanup
```

## Plan self-review

- Spec coverage: Tasks 1–3 implement local MOS-only routing, SSD path, auto fallback, scope, opt-out and no impact on other apps. Task 4 covers documentation, automated checks, live cold/warm/opt-out evidence and push.
- Placeholder scan: no TODO/TBD or unspecified test behavior remains. Dynamic record filenames are intentional because records must be created after real runs.
- Type consistency: `resolve_scene_list`, `scope_digest`, `build_environment` and `default_launch.py` are defined in Task 1 and consumed by Tasks 2–3; `no_nvrtc_cache` is parsed and threaded through Task 3 only.
