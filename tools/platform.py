"""Platform-specific utilities."""

import subprocess
import sys
from pathlib import Path


def open_file_explorer(path: str | Path) -> None:
    """Open the system file explorer at the given path."""
    path_str = str(path)
    if sys.platform == "win32":
        subprocess.run(["explorer", path_str], check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", path_str], check=False)
    else:
        subprocess.run(["xdg-open", path_str], check=False)
