"""Helpers for restoring persisted camera-pattern settings."""


def default_if_blank(value: str | None, default: str) -> str:
    """Use *default* when a persisted string is unset or blank."""
    if value is None or not value.strip():
        return default
    return value
