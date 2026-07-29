import importlib.util
import pathlib
import unittest

_MODULE_PATH = pathlib.Path(__file__).parents[1] / "benchmark.py"
_SPEC = importlib.util.spec_from_file_location("mos_benchmark", _MODULE_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
BenchmarkSettings = _MODULE.BenchmarkSettings


class BenchmarkSettingsTests(unittest.TestCase):
    def test_defaults_keep_benchmark_disabled(self):
        settings = BenchmarkSettings.from_values({})
        self.assertFalse(settings.enabled)
        self.assertEqual(settings.participant, "benchmark")
        self.assertTrue(settings.exit_on_complete)

    def test_cli_style_values_override_defaults(self):
        settings = BenchmarkSettings.from_values({
            "enabled": "true",
            "participant": "perf-run",
            "advanceDelaySec": "1.5",
            "standbyTimeoutSec": 12,
            "exitOnComplete": "false",
        })
        self.assertEqual(settings, BenchmarkSettings(True, "perf-run", 1.5, 12.0, False))


if __name__ == "__main__":
    unittest.main()
