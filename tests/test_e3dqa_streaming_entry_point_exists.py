"""The browser-streaming E3DQA entry point must remain buildable."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPOSITORY_ROOT / "source/apps/nycu.e3dqa_scene_viewer_streaming.kit"
REPO_TOML_PATH = REPOSITORY_ROOT / "repo.toml"


class E3dqaStreamingEntryPointTests(unittest.TestCase):
    def test_streaming_app_is_present_and_registered_for_building(self) -> None:
        self.assertTrue(APP_PATH.is_file())

        with REPO_TOML_PATH.open("rb") as repo_file:
            repo = tomllib.load(repo_file)

        self.assertIn(
            "${root}/source/apps/nycu.e3dqa_scene_viewer_streaming.kit",
            repo["repo_precache_exts"]["apps"],
        )


if __name__ == "__main__":
    unittest.main()
