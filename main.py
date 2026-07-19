"""MusicProfiler entry point."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(*, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)


def main() -> None:
    setup_logging()
    from ui.app import MusicProfilerApp
    app = MusicProfilerApp()
    app.run()


if __name__ == "__main__":
    main()
