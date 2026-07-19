"""Shared formatting utilities."""

from __future__ import annotations


def format_duration(ms: int) -> str:
    """Format milliseconds as ``m:ss``.

    Handles negative values by prepending a minus sign.
    """
    sign = "-" if ms < 0 else ""
    m, s = divmod(abs(ms) // 1000, 60)
    return f"{sign}{m}:{s:02d}"
