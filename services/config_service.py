"""Configuration service for MusicProfiler.

Provides loading, saving, and validating the application configuration,
including external tool paths (ffmpeg, ffprobe, demucs, um).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.exceptions import ConfigError

logger = logging.getLogger(__name__)

# Resolved once at import time — points at the repository / install root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_SRC = _PROJECT_ROOT / "config" / "default_config.json"


class ConfigService:
    """Manages application configuration: loading, saving, and validating tools.

    On first load, if no ``config.json`` exists in *config_dir*, the bundled
    ``config/default_config.json`` is copied there.
    """

    def __init__(self, config_dir: str | Path | None = None) -> None:
        """Initialise the config service.

        Args:
            config_dir: Directory where ``config.json`` is stored.
                Defaults to ``~/.musicprofiler/``.
        """
        if config_dir is None:
            self._config_dir = Path.home() / ".musicprofiler"
        else:
            self._config_dir = Path(config_dir)
        self._config_path = self._config_dir / "config.json"
        self._data: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def load(self) -> dict[str, Any]:
        """Load config from disk, copying the default template when absent.

        Returns:
            The parsed configuration dict.

        Raises:
            ConfigError: If the file cannot be read or parsed.
        """
        self._config_dir.mkdir(parents=True, exist_ok=True)

        if not self._config_path.exists():
            logger.info("No config at %s — copying default template.", self._config_path)
            try:
                shutil.copy2(_DEFAULT_CONFIG_SRC, self._config_path)
            except OSError as exc:
                raise ConfigError(
                    f"Failed to copy default config to {self._config_path}: {exc}"
                ) from exc

        try:
            self._data = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ConfigError(
                f"Failed to load config from {self._config_path}: {exc}"
            ) from exc

        logger.debug("Config loaded from %s.", self._config_path)
        return self._data

    def save(self, data: dict[str, Any]) -> None:
        """Write *data* atomically to ``config.json``.

        Writes to a temporary file first, then uses ``os.replace()`` so the
        target is never left in a half-written state.

        Raises:
            ConfigError: If the write or rename fails.
        """
        self._config_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self._config_path.with_name("config.json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(data, indent=4, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp_path, self._config_path)
        except OSError as exc:
            raise ConfigError(
                f"Failed to save config to {self._config_path}: {exc}"
            ) from exc
        self._data = data
        logger.debug("Config saved to %s.", self._config_path)

    # -- tool paths ---------------------------------------------------- #

    def get_tool_path(self, tool_name: str) -> str | None:
        """Return the configured filesystem path for *tool_name*, or ``None``."""
        return self._data.get("tools", {}).get(tool_name)

    def set_tool_path(self, tool_name: str, path: str | None) -> None:
        """Set *tool_name* to *path* and persist the config immediately.

        Pass ``None`` to unset a previously configured tool.
        """
        self._data.setdefault("tools", {})[tool_name] = path
        self.save(self._data)

    def get_default_playlist_id(self) -> int | None:
        """Return the configured default playlist id, if one is set."""
        playlist_id = self._data.get("playlist", {}).get("default_id")
        return playlist_id if isinstance(playlist_id, int) else None

    def set_default_playlist_id(self, playlist_id: int | None) -> None:
        """Persist the default playlist id or clear the preference."""
        self._data.setdefault("playlist", {})["default_id"] = playlist_id
        self.save(self._data)

    # -- validation ---------------------------------------------------- #

    def validate_tool(self, tool_name: str) -> bool:
        """Check a single tool by running its version flag.

        Tries ``{path} --version`` first and falls back to ``{path} -version``
        when the first form exits non-zero: ffmpeg / ffprobe reject the GNU
        style ``--version`` but accept the single-dash ``-version``.

        Returns:
            ``True`` if either invocation returned exit code 0, ``False``
            otherwise (including when the path is ``None`` or the process
            fails).
        """
        path = self.get_tool_path(tool_name)
        if not path:
            return False
        for flag in ("--version", "-version"):
            try:
                result = subprocess.run(
                    [path, flag],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    encoding="utf-8",
                    errors="replace",
                )
            except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
                logger.warning("Tool validation failed for %s: %s", path, exc)
                return False
            if result.returncode == 0:
                return True
        logger.warning(
            "Tool validation failed for %s: neither --version nor -version "
            "returned exit code 0",
            path,
        )
        return False

    def validate_tools(self) -> dict[str, bool]:
        """Validate every configured tool.

        Returns:
            Dict mapping each tool name to ``True`` / ``False``.
        """
        results: dict[str, bool] = {}
        for name in ("ffmpeg", "ffprobe", "demucs"):
            results[name] = self.validate_tool(name)
        return results

    # -- convenience accessors ----------------------------------------- #

    def get_workspace(self) -> Path:
        """Return the resolved (absolute) workspace path.

        Relative paths are resolved against the application root.
        """
        raw = self._data.get("workspace", "./workspace")
        ws_path = Path(raw).expanduser()
        if not ws_path.is_absolute():
            ws_path = _PROJECT_ROOT / ws_path
        return ws_path.resolve()

    def get_export_defaults(self) -> dict[str, Any]:
        """Return the ``export`` section of the configuration dict."""
        return self._data.get("export", {})
