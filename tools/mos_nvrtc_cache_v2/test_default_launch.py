#!/usr/bin/env python3
"""Focused tests for the default MOS NVRTC cache launcher."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name('default_launch.py')
SPEC = importlib.util.spec_from_file_location('default_launch', MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def load_repo_launch_module():
    """Load repo launch with only the Kit interfaces it imports stubbed."""
    omni = types.ModuleType('omni'); omni.__path__ = []
    repo = types.ModuleType('omni.repo'); repo.__path__ = []
    man = types.ModuleType('omni.repo.man'); man.__path__ = []
    man.resolve_tokens = lambda value: value.replace('${shell_ext}', '.sh').replace('${root}', '/repo')
    kit_template = types.ModuleType('omni.repo.kit_template'); kit_template.__path__ = []
    backend = types.ModuleType('omni.repo.kit_template.backend'); backend.read_toml = lambda path: {}
    frontend = types.ModuleType('omni.repo.kit_template.frontend')
    frontend.CLIInputColorPalette = type('CLIInputColorPalette', (), {})
    frontend.Separator = type('Separator', (), {})
    exceptions = types.ModuleType('omni.repo.man.exceptions')
    exceptions.QuietExpectedError = type('QuietExpectedError', (Exception,), {})
    fileutils = types.ModuleType('omni.repo.man.fileutils'); fileutils.rmtree = lambda path: None
    guidelines = types.ModuleType('omni.repo.man.guidelines'); guidelines.get_host_platform = lambda: 'linux-x86_64'
    utils = types.ModuleType('omni.repo.man.utils')
    utils.find_and_extract_package = lambda path: (path, path)
    utils.process_args_to_cmd = lambda args: ' '.join(args)
    utils.run_process = lambda *args, **kwargs: 0
    utils.run_process_return_output = lambda *args, **kwargs: (0, [])
    rich = types.ModuleType('rich'); rich.__path__ = []
    console = types.ModuleType('rich.console'); console.Console = lambda **kwargs: None
    theme = types.ModuleType('rich.theme'); theme.Theme = lambda: None
    omni.repo = repo; repo.man = man; repo.kit_template = kit_template
    kit_template.backend = backend; kit_template.frontend = frontend
    dependencies = {
        'omni': omni, 'omni.repo': repo, 'omni.repo.man': man,
        'omni.repo.kit_template': kit_template, 'omni.repo.kit_template.backend': backend,
        'omni.repo.kit_template.frontend': frontend, 'omni.repo.man.exceptions': exceptions,
        'omni.repo.man.fileutils': fileutils, 'omni.repo.man.guidelines': guidelines,
        'omni.repo.man.utils': utils, 'rich': rich, 'rich.console': console, 'rich.theme': theme,
    }
    launch_path = Path(__file__).parents[1] / 'repoman' / 'launch.py'
    spec = importlib.util.spec_from_file_location('repo_launch_under_test', launch_path)
    launch = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, dependencies):
        spec.loader.exec_module(launch)
    return launch


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
        scope = module.scope_digest(self.root / 'source/data/mos_scenes.json')
        cache_root = self.root / 'cache'
        shim = self.root / 'shim.so'
        renderer = self.root / 'renderer.so'
        env = module.build_environment(
            root, cache_root, scope, shim, renderer,
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


    def test_explicit_cache_scope_does_not_require_a_mos_scene_list(self):
        self.assertEqual(
            module.resolve_cache_scope(self.root, [], 'e3dqa-scene-viewer-v1'),
            'e3dqa-scene-viewer-v1',
        )

class RepoLaunchRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.build_dir = Path(self.temp_dir.name)
        self.launch = load_repo_launch_module()

    def tearDown(self):
        self.temp_dir.cleanup()

    def add_app(self, app_name):
        app_path = self.build_dir / f'{app_name}.sh'
        app_path.touch()
        return app_path

    def test_local_mos_launch_uses_cache_wrapper_with_one_app_command(self):
        app_path = self.add_app('nycu.mos_app.kit')
        with patch.object(self.launch, '_run_process') as run:
            self.launch.launch_kit('nycu.mos_app.kit', self.build_dir, {}, False, ['--foo'], False)

        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[:4], [sys.executable, '/repo/tools/mos_nvrtc_cache_v2/default_launch.py', '--app-command', str(app_path)])
        self.assertEqual(command[4:], ['--', '--foo'])

    def test_non_mos_launch_stays_direct(self):
        app_path = self.add_app('nycu.e3dqa_scene_viewer.kit')
        with patch.object(self.launch, '_run_process') as run:
            self.launch.launch_kit('nycu.e3dqa_scene_viewer.kit', self.build_dir, {}, False, [], False)

        self.assertEqual(run.call_args.args[0], [str(app_path)])

    def test_no_nvrtc_cache_keeps_local_mos_launch_direct(self):
        app_path = self.add_app('nycu.mos_app.kit')
        with patch.object(self.launch, '_run_process') as run:
            self.launch.launch_kit('nycu.mos_app.kit', self.build_dir, {}, False, [], True)

        self.assertEqual(run.call_args.args[0], [str(app_path)])


if __name__ == '__main__':
    unittest.main()
