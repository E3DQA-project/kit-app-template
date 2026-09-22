"""Regression checks for the E3DQA WebRTC streaming app entry point."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPOSITORY_ROOT / "source/apps/nycu.e3dqa_scene_viewer_streaming.kit"
REPO_TOML_PATH = REPOSITORY_ROOT / "repo.toml"


class E3dqaStreamingConfigTests(unittest.TestCase):
    def test_streaming_entry_point_exposes_the_expected_webrtc_endpoint(self) -> None:
        with APP_PATH.open("rb") as app_file:
            app = tomllib.load(app_file)

        dependencies = app["dependencies"]
        settings = app["settings"]

        self.assertIn("omni.kit.livestream.app", dependencies)
        self.assertEqual(settings["exts"]["omni.kit.livestream.app"]["primaryStream"]["streamType"], "webrtc")
        self.assertEqual(settings["exts"]["omni.kit.livestream.app"]["primaryStream"]["publicIp"], "140.113.214.34")
        self.assertEqual(settings["exts"]["omni.kit.livestream.app"]["primaryStream"]["signalPort"], 49100)
        self.assertEqual(settings["exts"]["omni.kit.livestream.app"]["primaryStream"]["streamPort"], 47998)

    def test_build_configuration_lists_the_streaming_entry_point(self) -> None:
        with REPO_TOML_PATH.open("rb") as repo_file:
            repo = tomllib.load(repo_file)

        apps = repo["repo_precache_exts"]["apps"]
        self.assertIn("${root}/source/apps/nycu.e3dqa_scene_viewer_streaming.kit", apps)


if __name__ == "__main__":
    unittest.main()
