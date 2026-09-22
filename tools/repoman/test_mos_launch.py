"""Regression tests for the MOS-only adapter around the upstream launcher."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("mos_launch.py")


def load_module():
    omni = types.ModuleType("omni"); omni.__path__ = []
    repo = types.ModuleType("omni.repo"); repo.__path__ = []
    kit_tools = types.ModuleType("omni.repo.kit_tools"); kit_tools.__path__ = []
    launch = types.ModuleType("omni.repo.kit_tools.launch")
    launch.resolve_tokens = lambda value: value.replace("${shell_ext}", ".sh").replace("${root}", "/repo")
    launch._get_repo_cmd = lambda: "repo"
    launch._quiet_error = lambda message: (_ for _ in ()).throw(RuntimeError(message))
    launch._run_process = lambda *args, **kwargs: 0
    launch.select_kit = lambda *args, **kwargs: "selected.kit"
    launch.add_container_arg = lambda parser: None
    launch.add_package_arg = lambda parser: None
    launch.add_name_arg = lambda parser: None
    launch.discover_kit_files = lambda path: []
    launch.expand_package = lambda path: Path(path)
    launch.launch_kit = lambda *args, **kwargs: None
    launch.nvidia_driver_check = lambda: None
    launch.launch_container = lambda *args, **kwargs: None
    launch.console = types.SimpleNamespace(print=lambda *args, **kwargs: None)
    launch.INFO_COLOR = ""
    repo.kit_tools = kit_tools
    kit_tools.launch = launch
    omni.repo = repo
    dependencies = {
        "omni": omni,
        "omni.repo": repo,
        "omni.repo.kit_tools": kit_tools,
        "omni.repo.kit_tools.launch": launch,
    }
    spec = importlib.util.spec_from_file_location("mos_launch_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, dependencies):
        spec.loader.exec_module(module)
    return module


class MosLaunchTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.build = Path(self.id().replace(".", "_"))

    def test_only_local_mos_is_wrapped(self):
        mos = self.build / "nycu.mos_app.kit.sh"
        viewer = self.build / "nycu.e3dqa_scene_viewer.kit.sh"
        with patch.object(Path, "is_file", return_value=True), patch.object(self.module.upstream, "_run_process") as run:
            self.module.launch_kit("nycu.mos_app.kit", self.build, {}, [])
            self.module.launch_kit("nycu.e3dqa_scene_viewer.kit", self.build, {}, [])

        mos_command, viewer_command = [call.args[0] for call in run.call_args_list]
        self.assertEqual(mos_command[:3], [sys.executable, "/repo/tools/mos_nvrtc_cache_v2/default_launch.py", "--app-command"])
        self.assertEqual(mos_command[3], str(mos))
        self.assertIn("--/exts/nycu.mos_app_extension/sceneListPath=/repo/source/data/mos_scenes.json", mos_command)
        self.assertEqual(viewer_command, [str(viewer)])

    def test_menu_selection_delegates_to_upstream_without_parsing_kit_toml(self):
        with patch.object(self.module.upstream, "select_kit", return_value="nycu.e3dqa_scene_viewer.kit") as select:
            chosen = self.module.choose_app(None, Path("build/apps"), {})

        self.assertEqual(chosen, "nycu.e3dqa_scene_viewer.kit")
        select.assert_called_once_with(Path("build/apps"), {})


if __name__ == "__main__":
    unittest.main()
