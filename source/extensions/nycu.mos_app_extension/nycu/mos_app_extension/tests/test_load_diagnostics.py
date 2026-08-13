import pathlib
import sys
import unittest
import importlib.util
from unittest import mock


PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

MODULE_PATH = PACKAGE_DIR / "load_diagnostics.py"
SPEC = importlib.util.spec_from_file_location("load_diagnostics", MODULE_PATH)
load_diagnostics = importlib.util.module_from_spec(SPEC)
sys.modules["load_diagnostics"] = load_diagnostics
SPEC.loader.exec_module(load_diagnostics)
_LoadDiagnostics = load_diagnostics._LoadDiagnostics


class LoadDiagnosticsTests(unittest.TestCase):
    def test_record_emits_stable_scene_fields_and_elapsed_time(self):
        clock = iter((10.0, 10.125))
        diag = _LoadDiagnostics(2, 7, "/tmp/example.usdz", clock=clock.__next__)

        with mock.patch("load_diagnostics.omni.log.info") as log_info:
            diag.begin()
            diag.record("STAGE_OPENED", prims=42)

        message = log_info.call_args.args[0]
        self.assertIn("[MOS_LOAD]", message)
        self.assertIn("event=STAGE_OPENED", message)
        self.assertIn("scene=2/7", message)
        self.assertIn("file=example.usdz", message)
        self.assertIn("elapsed_ms=125", message)
        self.assertIn("prims=42", message)

    def test_elapsed_time_is_zero_before_begin(self):
        diag = _LoadDiagnostics(1, 1, "/tmp/example.usdz", clock=lambda: 10.0)
        self.assertEqual(diag.elapsed_ms(), 0)


if __name__ == "__main__":
    unittest.main()
