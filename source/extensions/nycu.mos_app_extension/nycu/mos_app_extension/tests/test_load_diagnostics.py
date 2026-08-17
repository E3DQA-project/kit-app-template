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
_ReadinessGate = load_diagnostics._ReadinessGate
_RendererPhaseGate = load_diagnostics._RendererPhaseGate
_FrameStabilityGate = load_diagnostics._FrameStabilityGate
_DeferredGenerationGate = load_diagnostics._DeferredGenerationGate


class LoadDiagnosticsTests(unittest.TestCase):
    def test_record_emits_stable_scene_fields_and_elapsed_time(self):
        clock = iter((10.0, 10.125))
        diag = _LoadDiagnostics(
            2, 7, "/tmp/example.usdz", generation=3, clock=clock.__next__)

        with mock.patch("load_diagnostics.omni.log.info") as log_info:
            diag.begin()
            diag.record("STAGE_OPENED", prims=42)

        message = log_info.call_args.args[0]
        self.assertIn("[MOS_LOAD]", message)
        self.assertIn("event=STAGE_OPENED", message)
        self.assertIn("scene=2/7", message)
        self.assertIn("generation=3", message)
        self.assertIn("file=example.usdz", message)
        self.assertIn("elapsed_ms=125", message)
        self.assertIn("prims=42", message)

    def test_elapsed_time_is_zero_before_begin(self):
        diag = _LoadDiagnostics(1, 1, "/tmp/example.usdz", clock=lambda: 10.0)
        self.assertEqual(diag.elapsed_ms(), 0)

    def test_readiness_gate_only_allows_the_current_generation_once(self):
        gate = _ReadinessGate(4)

        self.assertFalse(gate.consume(3))
        self.assertTrue(gate.consume(4))
        self.assertFalse(gate.consume(4))

    def test_renderer_phase_gate_records_each_current_phase_once(self):
        gate = _RendererPhaseGate(7, ("FIRST_RENDER_COMMAND", "POST_PRESENT_FRAME_BUFFER"))

        self.assertFalse(gate.consume(6, "FIRST_RENDER_COMMAND"))
        self.assertTrue(gate.consume(7, "FIRST_RENDER_COMMAND"))
        self.assertFalse(gate.consume(7, "FIRST_RENDER_COMMAND"))
        self.assertTrue(gate.consume(7, "POST_PRESENT_FRAME_BUFFER"))
        self.assertTrue(gate.complete)
        self.assertFalse(gate.consume(7, "UNKNOWN_PHASE"))

    def test_frame_stability_gate_needs_consecutive_small_deltas_once(self):
        gate = _FrameStabilityGate(8, required_consecutive=2, max_delta=5)

        self.assertFalse(gate.consume(7, 0))
        self.assertFalse(gate.consume(8, 6))
        self.assertFalse(gate.consume(8, 5))
        self.assertTrue(gate.consume(8, 4))
        self.assertFalse(gate.consume(8, 0))

    def test_deferred_generation_gate_hands_one_matching_request_to_app_update(self):
        gate = _DeferredGenerationGate()

        gate.schedule(12)
        self.assertFalse(gate.consume(11))
        self.assertTrue(gate.consume(12))
        self.assertFalse(gate.consume(12))


if __name__ == "__main__":
    unittest.main()
