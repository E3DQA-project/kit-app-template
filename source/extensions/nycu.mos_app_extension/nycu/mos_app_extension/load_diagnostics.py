"""Dependency-light diagnostics for MOS scene loading."""

import os
import time
from typing import Callable, Optional

try:
    import omni.log as _omni_log
    import omni
except ImportError:
    class _FallbackLog:
        @staticmethod
        def info(_message: str) -> None:
            pass

    class _FallbackOmni:
        log = _FallbackLog()

    omni = _FallbackOmni()
    _omni_log = None


def _log_info(message: str) -> None:
    if _omni_log is not None:
        _omni_log.info(message)
    else:
        omni.log.info(message)


class _LoadDiagnostics:
    def __init__(
        self,
        scene_index: int,
        scene_total: int,
        scene_path: str,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.scene_index = scene_index
        self.scene_total = scene_total
        self.scene_path = scene_path
        self._clock = clock or time.perf_counter
        self._started_at: Optional[float] = None

    def begin(self) -> None:
        self._started_at = self._clock()

    def elapsed_ms(self) -> int:
        if self._started_at is None:
            return 0
        return max(0, round((self._clock() - self._started_at) * 1000))

    def record(self, event: str, **fields: object) -> None:
        details = {
            "event": event,
            "scene": f"{self.scene_index}/{self.scene_total}",
            "file": os.path.basename(self.scene_path),
            "elapsed_ms": self.elapsed_ms(),
        }
        details.update(fields)
        rendered = " ".join(f"{key}={value}" for key, value in details.items())
        _log_info(f"[MOS_LOAD] {rendered}")
