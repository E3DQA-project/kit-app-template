"""Regression checks for the E3DQA WebRTC streaming configuration."""

from __future__ import annotations

from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPOSITORY_ROOT / "source/apps/nycu.e3dqa_scene_viewer_streaming.kit"
REPO_TOML_PATH = REPOSITORY_ROOT / "repo.toml"


class E3DQAStreamingConfigTests(unittest.TestCase):
    def test_webrtc_endpoint_matches_the_reference_app(self) -> None:
        config = APP_PATH.read_text(encoding="utf-8")

        self.assertIn('"omni.kit.livestream.app" = { version = "10.1.0" }', config)
        self.assertIn('exts."omni.kit.livestream.app".primaryStream.streamType = "webrtc"', config)
        self.assertIn('exts."omni.kit.livestream.app".primaryStream.signalPort = 49100', config)
        self.assertIn('exts."omni.kit.livestream.app".primaryStream.streamPort = 47998', config)

    def test_streaming_app_is_precached_by_the_build(self) -> None:
        repo_config = REPO_TOML_PATH.read_text(encoding="utf-8")

        self.assertIn("[repo_precache_exts]", repo_config)
        self.assertIn("${root}/source/apps/nycu.e3dqa_scene_viewer_streaming.kit", repo_config)


if __name__ == "__main__":
    unittest.main()
