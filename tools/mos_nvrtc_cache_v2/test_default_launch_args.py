"""Argument-boundary regression test for the default MOS cache launcher."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("default_launch.py")
SPEC = importlib.util.spec_from_file_location("default_launch_args", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class DefaultLaunchArgumentTests(unittest.TestCase):
    def test_separator_is_not_forwarded_to_kit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scene_list = root / "mos_scenes.json"
            scene_list.write_text("[]")
            renderer = root / "libnrend.so"
            renderer.write_text("renderer")
            shim = root / "shim.so"
            shim.write_text("shim")
            process = type("Process", (), {"returncode": 0})()

            with (
                patch.object(module, "resolve_scene_list", return_value=scene_list),
                patch.object(module, "renderer_library", return_value=renderer),
                patch.object(module, "build_shim", return_value=shim),
                patch.object(module.subprocess, "run", return_value=process) as run,
            ):
                result = module.main([
                    "--app-command", "/opt/kit/kit", "--",
                    "--/exts/nycu.mos_app_extension/sceneListPath=/repo/source/data/mos_scenes.json",
                ])

        self.assertEqual(result, 0)
        self.assertEqual(
            run.call_args.args[0],
            ["/opt/kit/kit", "--/exts/nycu.mos_app_extension/sceneListPath=/repo/source/data/mos_scenes.json"],
        )


if __name__ == "__main__":
    unittest.main()
