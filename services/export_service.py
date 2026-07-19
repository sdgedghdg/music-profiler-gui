"""Export service — validate, transcode, normalise, merge."""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import asdict
from pathlib import Path

from core.enums import TaskStatus, TaskType
from core.exceptions import ExportError
from core.models import ExportConfig, Playlist, ProcessConfig, TaskInfo
from database.playlist_repo import PlaylistRepo
from services.task_service import TaskService
from tools.ffmpeg import FFmpeg

logger = logging.getLogger(__name__)


def _export_config_to_dict(config: ExportConfig) -> dict:
    """Convert ExportConfig to a JSON-serializable dict for task input_data."""
    return asdict(config)


def _execute_export(
    playlist: Playlist, config: ExportConfig, ffmpeg: FFmpeg, workspace: Path
) -> str:
    """Execute the full export pipeline.  Returns path to the output file."""
    timestamp = int(time.time())
    temp_dir = workspace / "temp" / f"export_{timestamp}"

    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Export started: playlist '%s' (%d items)",
                     playlist.name, len(playlist.items))

        # -- validate all source files exist before any work ----------------
        for item in playlist.items:
            if not Path(item.file_path).exists():
                raise ExportError(
                    f"Song file not found: {item.file_path}"
                )

        # -- build ffmpeg transcode config ---------------------------------
        transcode_cfg = ProcessConfig(
            output_format=config.output_format,
            bitrate_bps=config.bitrate_bps,
            sample_rate_hz=config.sample_rate_hz,
            channels=2,
        )

        # -- transcode (and optionally normalise) each item -----------------
        processed: list[Path] = []
        for i, item in enumerate(playlist.items):
            temp_file = temp_dir / f"{i:04d}_{item.id}.{config.output_format}"
            logger.info("Transcoding %d/%d: %s",
                        i + 1, len(playlist.items), item.title)
            ffmpeg.transcode(item.file_path, temp_file, transcode_cfg)

            if config.normalize_loudness:
                norm_file = temp_dir / f"{i:04d}_{item.id}_norm.{config.output_format}"
                logger.info("Normalising: %s", item.title)
                ffmpeg.normalize_loudness(temp_file, norm_file)
                temp_file = norm_file

            processed.append(temp_file)

        # -- merge into final output ----------------------------------------
        safe_name = (playlist.name.strip() or "playlist").replace(" ", "_")
        safe_name = safe_name.replace("/", "_").replace("\\", "_")
        export_dir = workspace / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        output_path = export_dir / f"{safe_name}_{timestamp}.{config.output_format}"

        logger.info("Merging %d files into %s", len(processed), output_path)
        ffmpeg.concat(
            [str(p) for p in processed], str(output_path),
            format=config.output_format,
        )

        logger.info("Export complete: %s", output_path)
        return str(output_path)

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info("Cleaned up temp directory: %s", temp_dir)


class ExportService:
    """Service for creating broadcast-ready playlist exports."""

    def __init__(
        self,
        playlist_repo: PlaylistRepo,
        task_service: TaskService,
        ffmpeg: FFmpeg,
        workspace: Path,
    ) -> None:
        """Initialise with repos, FFmpeg wrapper, and workspace directory."""
        self._playlist_repo = playlist_repo
        self._task_service = task_service
        self._ffmpeg = ffmpeg
        self._workspace = workspace

    def export(self, playlist_id: int, config: ExportConfig) -> TaskInfo:
        """Create and enqueue an export task."""
        playlist = self._playlist_repo.get_by_id(playlist_id)

        if not playlist.items:
            raise ExportError(
                f"Playlist '{playlist.name}' (id={playlist_id}) has no items "
                f"to export"
            )

        task = TaskInfo(
            id=None,
            task_type=TaskType.EXPORT,
            status=TaskStatus.PENDING,
            progress=0.0,
            input_data={
                "playlist_id": playlist_id,
                "config": _export_config_to_dict(config),
            },
        )
        task = self._task_service.enqueue(task)
        logger.info("Created export task id=%d for playlist '%s'",
                     task.id, playlist.name)
        return task

    def get_export_path(self, playlist_name: str, format: str = "mp3") -> Path:
        """Return the default export output path for a playlist."""
        safe = (playlist_name.strip() or "playlist").replace(" ", "_")
        safe = safe.replace("/", "_").replace("\\", "_")
        return self._workspace / "export" / f"{safe}.{format}"
