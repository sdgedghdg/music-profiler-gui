"""Base class for external tool wrappers."""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass

from core.exceptions import ToolExecutionError, ToolNotFoundError

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: int


def require_runner(runner: ToolRunner | None) -> ToolRunner:
    """Return *runner* or raise ToolNotFoundError when it is ``None``.

    用于 FFmpeg / FFprobe / Demucs 的判空：工具路径未配置时上层会传入
    ``None``，此时尽早抛出语义明确的 ToolNotFoundError，而不是等到调用
    ``None.run(...)`` 才炸出 AttributeError。
    """
    if runner is None:
        raise ToolNotFoundError("Tool binary path is not configured")
    return runner


class ToolRunner:
    """Common subprocess runner with timeout, logging, and error handling."""

    def __init__(self, binary_path: str, *, default_timeout: int = 600) -> None:
        self.binary_path = binary_path
        self.default_timeout = default_timeout

    def run(self, args: list[str], *, timeout: int | None = None) -> ToolResult:
        """Run the tool binary with *args*.

        Raises ToolExecutionError on timeout or non-zero returncode.
        """
        if self.binary_path is None:
            raise ToolNotFoundError("Tool binary path is not configured")

        cmd = [self.binary_path] + args
        effective_timeout = timeout if timeout is not None else self.default_timeout

        logger.debug("Running: %s", cmd)
        start = time.monotonic()

        try:
            completed = subprocess.run(
                cmd, capture_output=True, text=True, timeout=effective_timeout,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.error("Tool timed out after %d ms: %s", elapsed_ms, cmd)
            raise ToolExecutionError(
                f"Tool timed out after {effective_timeout}s: {' '.join(cmd)}"
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.debug("Completed in %d ms (returncode=%d)", elapsed_ms, completed.returncode)

        if completed.returncode != 0:
            raise ToolExecutionError(
                f"Tool exited with code {completed.returncode}: {' '.join(cmd)}"
                + (
                    f"\nstderr: {completed.stderr.strip()}"
                    if completed.stderr.strip()
                    else ""
                )
            )

        return ToolResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_ms=elapsed_ms,
        )
