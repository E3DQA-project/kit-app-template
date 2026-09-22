#!/usr/bin/env python3
"""Launch MOS with the default NVRTC cache interposer enabled."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Mapping


ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = Path('/mnt/gen5_SSD/pierce/mos-nvrtc-cache-v2')
SCENE_LIST_PREFIX = '--/exts/nycu.mos_app_extension/sceneListPath='


def resolve_scene_list(root: Path, kit_args: list[str]) -> Path:
    explicit = next(
        (arg[len(SCENE_LIST_PREFIX):] for arg in kit_args if arg.startswith(SCENE_LIST_PREFIX)),
        None,
    )
    candidate = Path(explicit) if explicit else root / 'source/data/mos_scenes.json'
    if not candidate.is_file():
        raise ValueError(f'scene list does not exist: {candidate}')
    return candidate.resolve()


def scope_digest(scene_list: Path) -> str:
    return hashlib.sha256(scene_list.read_bytes()).hexdigest()


def resolve_cache_scope(root: Path, kit_args: list[str], explicit_scope: str | None) -> str:
    """Use an explicit app policy scope, or MOS's content-addressed scene list."""
    if explicit_scope:
        return explicit_scope
    return scope_digest(resolve_scene_list(root, kit_args))


def build_environment(
    root: Path,
    cache_root: Path,
    scope: str,
    shim: Path,
    renderer: Path,
    inherited: Mapping[str, str],
) -> dict[str, str]:
    environment = {
        key: value
        for key, value in inherited.items()
        if key != 'LD_PRELOAD' and not key.startswith('MOS_V2_')
    }
    environment.update(
        LD_PRELOAD=str(shim),
        MOS_V2_LIBRARY=str(renderer),
        MOS_V2_DIR=str(cache_root),
        MOS_V2_SCOPE=scope,
        MOS_V2_MODE='auto',
        MOS_V2_PRIVATE_EXPERIMENT='1',
        OMNI_REPO_ROOT=str(root),
    )
    return environment


def renderer_library(root: Path) -> Path:
    matches = sorted(
        (root / '_build/linux-x86_64/release/extscache').glob(
            'omni.hydra.rtx-*/bin/deps/libnrend.so'
        )
    )
    if not matches:
        raise FileNotFoundError('MOS renderer library libnrend.so was not found')
    return matches[-1].resolve()


def build_shim(root: Path, cache_root: Path, renderer: Path) -> Path:
    renderer_digest = hashlib.sha256(renderer.read_bytes()).hexdigest()
    shim = cache_root / 'shim' / renderer_digest / 'libmos_nvrtc_cache_v2.so'
    shim.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=shim.parent, prefix='.libmos_nvrtc_cache_v2.', delete=False) as temp:
        temporary_shim = Path(temp.name)
    try:
        subprocess.run(
            [
                'g++', '-std=c++17', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                '-Itools/mos_nvrtc_cache/include',
                'tools/mos_nvrtc_cache_v2/interposer.cpp',
                'tools/mos_nvrtc_cache/src/key.cpp', '-ldl', '-pthread', '-o', str(temporary_shim),
            ],
            cwd=root,
            check=True,
        )
        os.replace(temporary_shim, shim)
    finally:
        temporary_shim.unlink(missing_ok=True)
    return shim


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-command', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, default=CACHE_ROOT)
    parser.add_argument('--cache-scope')
    parser.add_argument('kit_args', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    kit_args = args.kit_args[1:] if args.kit_args[:1] == ['--'] else args.kit_args
    scope = resolve_cache_scope(ROOT, kit_args, args.cache_scope)
    renderer = renderer_library(ROOT)
    cache_root = args.cache_root.resolve()
    shim = build_shim(ROOT, cache_root, renderer)
    cache_dir = cache_root / 'artifacts' / scope
    cache_dir.mkdir(parents=True, exist_ok=True)
    environment = build_environment(ROOT, cache_dir, scope, shim, renderer, os.environ)
    return subprocess.run([str(args.app_command), *kit_args], cwd=ROOT, env=environment).returncode


if __name__ == '__main__':
    sys.exit(main())
