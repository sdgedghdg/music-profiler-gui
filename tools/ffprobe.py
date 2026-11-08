"""FFprobe wrapper for audio metadata extraction."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.exceptions import ToolExecutionError
from tools.base import ToolRunner, require_runner

logger = logging.getLogger(__name__)


class FFprobe:
    """Wrapper around ffprobe for reading audio file metadata."""

    def __init__(self, runner: ToolRunner | None = None) -> None:
        self._runner = runner

    def probe(self, file_path: str | Path) -> dict:
        """Return parsed JSON metadata for *file_path*."""
        runner = require_runner(self._runner)
        file_path = Path(file_path)
        args = [
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ]
        logger.info("Probing: %s", file_path)
        result = runner.run(args)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(
                f"Failed to parse ffprobe output for {file_path}: {exc}"
            ) from exc
