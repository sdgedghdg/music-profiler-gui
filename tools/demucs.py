"""Demucs wrapper for music source separation (vocals / accompaniment)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from core.exceptions import ToolExecutionError
from tools.base import ToolRunner, require_runner

logger = logging.getLogger(__name__)


@dataclass
class DemucsResult:
    """Output paths from a Demucs separation run."""

    vocals_path: str
    other_path: str
    output_dir: str


class Demucs:
    """Wrapper around demucs for source separation."""

    def __init__(self, runner: ToolRunner | None = None) -> None:
        self._runner = runner

    def separate(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        model: str = "htdemucs",
    ) -> DemucsResult:
        """Run two-stem (vocals) separation and return the result paths."""
        runner = require_runner(self._runner)
        input_path = Path(input_path)
        output_dir = Path(output_dir)

        args = [
            "--two-stems", "vocals",
            "-o", str(output_dir),
            str(input_path),
        ]
        # Prepend model name if non-default
        if model != "htdemucs":
            args.insert(0, model)
            args.insert(0, "-n")

        logger.info("Separating: %s (model=%s)", input_path, model)
        runner.run(args)

        # Demucs writes to: <output_dir>/<model>/<input_stem>/
        model_dir = output_dir / model
        stem_dir = model_dir / input_path.stem

        # Search for vocals / no_vocals files in the expected location
        vocals_candidates = sorted(stem_dir.glob("vocals.*"))
        other_candidates = sorted(stem_dir.glob("no_vocals.*"))

        if not vocals_candidates:
            raise ToolExecutionError(
                f"Demucs completed but no vocals file found under {stem_dir}"
            )
        if not other_candidates:
            raise ToolExecutionError(
                f"Demucs completed but no accompaniment file found under {stem_dir}"
            )

        return DemucsResult(
            vocals_path=str(vocals_candidates[0]),
            other_path=str(other_candidates[0]),
            output_dir=str(stem_dir),
        )
