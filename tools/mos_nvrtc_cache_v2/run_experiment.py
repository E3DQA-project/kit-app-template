#!/usr/bin/env python3
"""Single-scene MOS experiment. Generated run logs are distinct from source edits."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '_mos_asset_loading_experiment/nvrtc-cache-v2'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode', choices=['seed', 'replay'], required=True)
    ap.add_argument('--scene', type=Path, required=True)
    ap.add_argument('--prepare-only', action='store_true')
    args = ap.parse_args()
    scene = args.scene.resolve(strict=True)
    renderer = (ROOT / '_build/linux-x86_64/release/extscache/omni.hydra.rtx-1.0.4+698af100.lx64.r/bin/deps/libnrend.so').resolve(strict=True)
    kit = ROOT / '_build/linux-x86_64/release/kit/kit'
    app = ROOT / '_build/linux-x86_64/release/apps/nycu.mos_app.kit'
    build = BASE / 'build'
    build.mkdir(parents=True, exist_ok=True)
    shim = build / 'libmos_nvrtc_cache_v2.so'
    subprocess.run(['g++', '-std=c++17', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                    '-Itools/mos_nvrtc_cache/include', 'tools/mos_nvrtc_cache_v2/interposer.cpp',
                    'tools/mos_nvrtc_cache/src/key.cpp', '-ldl', '-pthread', '-o', str(shim)], cwd=ROOT, check=True)
    print('Hashing scene before launch, outside scene-load timing.', flush=True)
    scope = digest(scene)
    cache = BASE / 'artifacts' / scope
    cache.mkdir(parents=True, exist_ok=True)
    if args.mode == 'replay' and not list(cache.glob('*.bin')):
        raise SystemExit('No cold artifacts: complete a seed run first.')
    stamp = datetime.datetime.now().astimezone().strftime('%Y%m%d-%H%M%S-%f')
    run = BASE / (stamp + '-' + args.mode)
    run.mkdir()
    scenes = run / 'scenes.json'
    scenes.write_text(json.dumps({'version': 1, 'scenes': [str(scene)]}))
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('MOS_NVRTC_', 'MOS_V2_')) or key == 'LD_PRELOAD':
            env.pop(key)
    env.update(LD_PRELOAD=str(shim), MOS_V2_LIBRARY=str(renderer), MOS_V2_DIR=str(cache),
               MOS_V2_SCOPE=scope, MOS_V2_MODE=args.mode, MOS_V2_PRIVATE_EXPERIMENT='1', OMNI_REPO_ROOT=str(ROOT))
    command = [str(kit), str(app), f'--/exts/nycu.mos_app_extension/sceneListPath={scenes}']
    manifest = dict(mode=args.mode, scene=str(scene), scene_sha256=scope, renderer=str(renderer),
                    renderer_sha256=digest(renderer), shim_sha256=digest(shim), command=command,
                    cache=str(cache), run=str(run), started=datetime.datetime.now().astimezone().isoformat(),
                    limitation='Private CPEx inputs are incompletely understood; single-scene experimental replay only.')
    (run / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print('RUN_DIR=' + str(run), flush=True)
    if args.prepare_only:
        print('PREPARED: GUI not launched.', flush=True)
        return 0
    record = ROOT / 'docs/records' / (stamp + '-mos-nvrtc-v2-' + args.mode + '.md')
    code, kit_log = None, None
    with record.open('x') as f, (run / 'console.log').open('x') as log:
        f.write('# MOS NVRTC v2 live run\n\nStatus: running; no success claim yet.\n\n')
        f.write('```json\n' + json.dumps(manifest, indent=2) + '\n```\n\n## Compiler events\n\n```text\n')
        f.flush()
        child = subprocess.Popen(command, env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, errors='replace', bufsize=1)
        (run / 'pid').write_text(str(child.pid))
        try:
            for line in child.stdout:
                log.write(line); log.flush()
                print(line, end='', flush=True)
                if 'MOS_V2 ' in line:
                    f.write(line); f.flush()
                match = re.search(r'Logging to file: (.*)', line)
                if match:
                    kit_log = Path(match.group(1).strip())
            code = child.wait()
        except KeyboardInterrupt:
            # Terminal SIGINT also reaches Kit. Preserve output while waiting for shutdown.
            rest, _ = child.communicate()
            log.write(rest or '')
            code = child.returncode
        finally:
            f.write('```\n\n## Kit scene checkpoints\n\n```text\n')
            if kit_log and kit_log.is_file():
                text = kit_log.read_text(errors='replace')
                (run / 'kit.log').write_text(text)
                for line in text.splitlines():
                    if re.search(r'event=(BEGIN|STAGE_OPENED|RENDER_STABLE|VIEWER_STAGE_LOADED|FIRST_USER_ACTION)\b', line):
                        f.write(line + '\n')
            f.write(f'```\n\nExit observed: {datetime.datetime.now().astimezone().isoformat()}, code={code}.\n')
            f.write('Functional rendering and replay success require review and user observation.\n')
    print('RECORD=' + str(record), flush=True)
    return code if code is not None else 1


if __name__ == '__main__':
    sys.exit(main())
