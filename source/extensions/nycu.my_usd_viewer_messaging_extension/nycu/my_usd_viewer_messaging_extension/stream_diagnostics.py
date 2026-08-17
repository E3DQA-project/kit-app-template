"""Dependency-light lifecycle diagnostics for the viewer streaming gate."""

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


class _StreamingStateGate:
    """Emit only transitions in a streamer's busy state."""

    def __init__(self) -> None:
        self._is_busy: Optional[bool] = None

    def observe(self, is_busy: bool) -> Optional[str]:
        if self._is_busy == is_busy:
            return None
        self._is_busy = is_busy
        return "STREAMING_BUSY" if is_busy else "STREAMING_IDLE"


class _LoadingStatusGate:
    """Emit only changed USD loading-status snapshots."""

    def __init__(self) -> None:
        self._previous: Optional[tuple[str, int, int]] = None

    def observe(self, message: str, files_loaded: int, total_files: int) -> bool:
        current = (message, files_loaded, total_files)
        if current == self._previous:
            return False
        self._previous = current
        return True


class _StreamDiagnostics:
    def __init__(
        self, generation: int, stage_url: str, clock: Optional[Callable[[], float]] = None
    ) -> None:
        self._generation = generation
        self._stage_url = stage_url
        self._clock = clock or time.perf_counter
        self._started_at = self._clock()

    def elapsed_ms(self) -> int:
        return max(0, round((self._clock() - self._started_at) * 1000))

    def record(self, event: str, **fields: object) -> None:
        details = {
            "event": event,
            "generation": self._generation,
            "file": os.path.basename(self._stage_url),
            "elapsed_ms": self.elapsed_ms(),
        }
        details.update(fields)
        rendered = " ".join(f"{key}={value}" for key, value in details.items())
        _log_info(f"[MOS_STREAM] {rendered}")
