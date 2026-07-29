"""Configuration helpers for the non-interactive MOS benchmark."""

from dataclasses import dataclass
from typing import Mapping


def _bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _float(value: object, default: float) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class BenchmarkSettings:
    enabled: bool = False
    participant: str = "benchmark"
    advance_delay_sec: float = 0.25
    standby_timeout_sec: float = 180.0
    exit_on_complete: bool = True

    @classmethod
    def from_values(cls, values: Mapping[str, object]) -> "BenchmarkSettings":
        participant = str(values.get("participant", "benchmark")).strip() or "benchmark"
        return cls(
            enabled=_bool(values.get("enabled"), False),
            participant=participant,
            advance_delay_sec=_float(values.get("advanceDelaySec"), 0.25),
            standby_timeout_sec=_float(values.get("standbyTimeoutSec"), 180.0),
            exit_on_complete=_bool(values.get("exitOnComplete"), True),
        )
