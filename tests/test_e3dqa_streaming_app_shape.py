"""Ensure the streaming configuration remains a runnable Kit application."""

from __future__ import annotations

from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPOSITORY_ROOT / "source/apps/nycu.e3dqa_scene_viewer_streaming.kit"
PREMAKE_PATH = REPOSITORY_ROOT / "premake5.lua"


class E3DQAStreamingAppShapeTests(unittest.TestCase):
    def test_streaming_config_is_a_full_editor_application(self) -> None:
        config = APP_PATH.read_text(encoding="utf-8")

        self.assertIn('template_name = "kit_base_editor"', config)
        self.assertIn('type = "ApplicationTemplate"', config)
        self.assertIn('"nycu.camera_conventions" = {}', config)
        self.assertNotIn('"nycu.e3dqa_scene_viewer" = {}', config)

    def test_streaming_application_has_a_built_launcher_target(self) -> None:
        premake = PREMAKE_PATH.read_text(encoding="utf-8")

        self.assertIn('define_app("nycu.e3dqa_scene_viewer_streaming.kit")', premake)


if __name__ == "__main__":
    unittest.main()
