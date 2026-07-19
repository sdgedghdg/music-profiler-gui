"""Transcode executor — batch audio transcoding."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from core.enums import TaskStatus
from core.exceptions import ToolExecutionError
from core.models import TaskInfo
from database.song_repo import SongRepo
from database.task_repo import TaskRepo
from tools.ffmpeg import FFmpeg, ProcessConfig as FFmpegConfig

logger = logging.getLogger(__name__)


class TranscodeExecutor:
    """Runs batch transcode tasks.  All DB access through worker-owned repos."""

    def __init__(
        self,
        song_repo: SongRepo,
        ffmpeg: FFmpeg,
        workspace: Path,
        task_repo: TaskRepo,
        is_shutdown: Callable[[], bool],
    ) -> None:
        self._song_repo = song_repo
        self._ffmpeg = ffmpeg
        self._workspace = workspace
        self._task_repo = task_repo
        self._is_shutdown = is_shutdown

    def execute(self, task: TaskInfo) -> None:
        """Run a batch transcode task.  input_data: {"song_ids": [1,…], "config": {…}}."""
        input_data: dict = task.input_data or {}
        song_ids: list[int] = input_data.get("song_ids", [])
        config: dict = input_data.get("config", {})

        if not song_ids:
            logger.info("No song_ids in transcode task id=%d", task.id)
            self._task_repo.update_output(
                task.id, {"new_paths": [], "processed_count": 0, "failed_count": 0},
            )
            return

        output_format = config.get("output_format") or config.get("format", "mp3")
        ff_config = FFmpegConfig(
            format=output_format,
            bitrate_bps=config.get("bitrate_bps", 320000),
            sample_rate_hz=config.get("sample_rate_hz", 44100),
            channels=config.get("channels", 2),
            target_loudness_lufs=config.get("target_loudness_lufs"),
        )

        output_dir = self._workspace / "transcoded"
        output_dir.mkdir(parents=True, exist_ok=True)

        new_paths: list[str] = []
        failed_ids: list[int] = []
        total = len(song_ids)

        for i, song_id in enumerate(song_ids):
            if self._is_shutdown():
                logger.info("Shutdown — stopping transcode after %d/%d songs", i, total)
                break
            try:
                song = self._song_repo.get_by_id(song_id)
            except Exception:
                logger.exception("Failed to load song id=%d", song_id)
                failed_ids.append(song_id)
                continue

            output_path = output_dir / f"{song.id}.{output_format}"
            try:
                self._ffmpeg.transcode(song.file_path, output_path, ff_config)
            except Exception:
                logger.exception("Transcode failed song id=%d", song_id)
                failed_ids.append(song_id)
                continue

            new_paths.append(str(output_path))
            song.file_path = str(output_path)
            song.format = output_format
            try:
                self._song_repo.update(song)
            except Exception:
                logger.exception("Failed to update song id=%d after transcode", song_id)

            progress = (i + 1) / total
            self._task_repo.update_status(task.id, TaskStatus.RUNNING, progress=progress)
            task.progress = progress
            logger.info("Transcode %d/%d (%.0f%%)", i + 1, total, progress * 100)

        task.output_data = {
            "new_paths": new_paths,
            "processed_count": len(new_paths),
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids,
            "output_format": output_format,
        }
        self._task_repo.update_output(task.id, task.output_data)

        if not new_paths and song_ids:
            raise ToolExecutionError(f"All {len(song_ids)} transcode(s) failed")
