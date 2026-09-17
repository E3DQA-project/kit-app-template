#!/usr/bin/env python3
"""Focused tests for the default MOS NVRTC cache launcher."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name('default_launch.py')
SPEC = importlib.util.spec_from_file_location('default_launch', MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class DefaultLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write(self, relative_path, content):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def make_root(self, default_list):
        self.write('source/data/mos_scenes.json', b'{"scenes":[]}')
        return self.root

    def test_explicit_scene_list_beats_source_default(self):
        root = self.make_root(default_list='default.json')
        custom = self.write('custom.json', b'{"scenes":["custom.usdz"]}')
        chosen = module.resolve_scene_list(
            root, [f'--/exts/nycu.mos_app_extension/sceneListPath={custom}']
        )
        self.assertEqual(chosen, custom.resolve())

    def test_scope_is_content_digest_not_path_digest(self):
        first = self.write('one.json', b'{"scenes":["a.usdz"]}')
        second = self.write('two.json', b'{"scenes":["a.usdz"]}')
        self.assertEqual(module.scope_digest(first), module.scope_digest(second))

    def test_environment_is_auto_mode_and_strips_inherited_preload(self):
        root = self.make_root(default_list='default.json')
        list_path = self.root / 'source/data/mos_scenes.json'
        cache_root = self.root / 'cache'
        shim = self.root / 'shim.so'
        renderer = self.root / 'renderer.so'
        env = module.build_environment(
            root, cache_root, list_path, shim, renderer,
            {'LD_PRELOAD': '/unrelated.so', 'MOS_V2_MODE': 'replay', 'KEEP': 'yes'},
        )
        self.assertEqual(env['MOS_V2_MODE'], 'auto')
        self.assertEqual(env['MOS_V2_DIR'], str(cache_root))
        self.assertEqual(env['LD_PRELOAD'], str(shim))
        self.assertEqual(env['KEEP'], 'yes')

    def test_missing_explicit_scene_list_is_rejected_before_launch(self):
        root = self.make_root(default_list='default.json')
        with self.assertRaisesRegex(ValueError, 'scene list'):
            module.resolve_scene_list(
                root, ['--/exts/nycu.mos_app_extension/sceneListPath=/missing.json']
            )


if __name__ == '__main__':
    unittest.main()
