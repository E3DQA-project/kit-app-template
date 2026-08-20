import importlib.util
import pathlib
import sys
import unittest


PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = PACKAGE_DIR / "stream_diagnostics.py"
SPEC = importlib.util.spec_from_file_location("stream_diagnostics", MODULE_PATH)
stream_diagnostics = importlib.util.module_from_spec(SPEC)
sys.modules["stream_diagnostics"] = stream_diagnostics
SPEC.loader.exec_module(stream_diagnostics)
_StreamingStateGate = stream_diagnostics._StreamingStateGate
_LoadingStatusGate = stream_diagnostics._LoadingStatusGate
_ActivityCaptureGate = stream_diagnostics._ActivityCaptureGate
_NvtxRangeGate = stream_diagnostics._NvtxRangeGate
_begin_nvtx_range = stream_diagnostics._begin_nvtx_range
_end_nvtx_range = stream_diagnostics._end_nvtx_range


class StreamDiagnosticsTests(unittest.TestCase):
    def test_streaming_state_gate_emits_only_transitions(self):
        gate = _StreamingStateGate()

        self.assertEqual(gate.observe(True), "STREAMING_BUSY")
        self.assertIsNone(gate.observe(True))
        self.assertEqual(gate.observe(False), "STREAMING_IDLE")
        self.assertIsNone(gate.observe(False))

    def test_loading_status_gate_emits_only_changed_snapshots(self):
        gate = _LoadingStatusGate()

        self.assertTrue(gate.observe("Downloading", 1, 5))
        self.assertFalse(gate.observe("Downloading", 1, 5))
        self.assertTrue(gate.observe("Downloading", 2, 5))
        self.assertTrue(gate.observe("Finalizing", 2, 5))

    def test_activity_capture_gate_releases_exactly_one_token(self):
        gate = _ActivityCaptureGate()
        released = []

        self.assertTrue(gate.begin(lambda: 73))
        self.assertFalse(gate.begin(lambda: 99))
        self.assertTrue(gate.end(released.append))
        self.assertEqual(released, [73])
        self.assertFalse(gate.end(released.append))

    def test_nvtx_range_gate_opens_and_closes_once(self):
        gate = _NvtxRangeGate()
        calls = []

        self.assertTrue(gate.begin(lambda: calls.append("push")))
        self.assertFalse(gate.begin(lambda: calls.append("duplicate-push")))
        self.assertTrue(gate.end(lambda: calls.append("pop")))
        self.assertEqual(calls, ["push", "pop"])
        self.assertFalse(gate.end(lambda: calls.append("duplicate-pop")))

    def test_nvtx_range_helpers_use_profiler_begin_and_end(self):
        class Profiler:
            def __init__(self):
                self.calls = []

            def begin(self, mask, name):
                self.calls.append(("begin", mask, name))

            def end(self, mask):
                self.calls.append(("end", mask))

        gate = _NvtxRangeGate()
        profiler = Profiler()

        self.assertTrue(_begin_nvtx_range(gate, profiler, "MOS_SCENE_ASSETS_LOADING"))
        self.assertTrue(_end_nvtx_range(gate, profiler))
        self.assertEqual(
            profiler.calls,
            [("begin", 1, "MOS_SCENE_ASSETS_LOADING"), ("end", 1)],
        )


if __name__ == "__main__":
    unittest.main()
