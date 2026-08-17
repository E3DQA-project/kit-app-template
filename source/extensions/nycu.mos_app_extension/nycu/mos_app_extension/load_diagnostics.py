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
        generation: int = 0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.scene_index = scene_index
        self.scene_total = scene_total
        self.scene_path = scene_path
        self.generation = generation
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
            "generation": self.generation,
            "scene": f"{self.scene_index}/{self.scene_total}",
            "file": os.path.basename(self.scene_path),
            "elapsed_ms": self.elapsed_ms(),
        }
        details.update(fields)
        rendered = " ".join(f"{key}={value}" for key, value in details.items())
        _log_info(f"[MOS_LOAD] {rendered}")


class _ReadinessGate:
    """Accept the first ready callback for one active scene generation."""

    def __init__(self, generation: int) -> None:
        self._generation = generation
        self._consumed = False

    def consume(self, generation: int) -> bool:
        if self._consumed or generation != self._generation:
            return False
        self._consumed = True
        return True


class _RendererPhaseGate:
    """Accept each renderer phase once for one active scene generation."""

    def __init__(self, generation: int, phases: tuple[str, ...]) -> None:
        self._generation = generation
        self._remaining = set(phases)

    @property
    def complete(self) -> bool:
        return not self._remaining

    def consume(self, generation: int, phase: str) -> bool:
        if generation != self._generation or phase not in self._remaining:
            return False
        self._remaining.remove(phase)
        return True


class _FrameStabilityGate:
    """Accept one generation after consecutive sampled frames change only slightly."""

    def __init__(self, generation: int, required_consecutive: int, max_delta: int) -> None:
        self._generation = generation
        self._required_consecutive = required_consecutive
        self._max_delta = max_delta
        self._consecutive = 0
        self._consumed = False

    def consume(self, generation: int, delta: int) -> bool:
        if self._consumed or generation != self._generation:
            return False
        if delta > self._max_delta:
            self._consecutive = 0
            return False
        self._consecutive += 1
        if self._consecutive < self._required_consecutive:
            return False
        self._consumed = True
        return True


class _DeferredGenerationGate:
    """Hand one generation from a non-app callback to the next app update."""

    def __init__(self) -> None:
        self._pending_generation: Optional[int] = None

    def schedule(self, generation: int) -> None:
        self._pending_generation = generation

    def clear(self) -> None:
        self._pending_generation = None

    def consume(self, generation: int) -> bool:
        if self._pending_generation != generation:
            return False
        self._pending_generation = None
        return True
