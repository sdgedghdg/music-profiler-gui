"""Demucs executor — vocal/accompaniment separation via Demucs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from core.enums import TaskStatus
from core.exceptions import ToolExecutionError
from core.models import SeparatedTrack, TaskInfo
from database.separated_track_repo import SeparatedTrackRepo
from database.song_repo import SongRepo
from database.task_repo import TaskRepo
from tools.demucs import Demucs
from tools.ffmpeg import FFmpeg

logger = logging.getLogger(__name__)


class DemucsExecutor:
    """Runs Demucs source-separation tasks.  All DB access through worker-owned repos."""

    def __init__(
        self,
        song_repo: SongRepo,
        ffmpeg: FFmpeg,
        demucs: Demucs,
        workspace: Path,
        task_repo: TaskRepo,
        is_shutdown: Callable[[], bool],
        separated_track_repo: SeparatedTrackRepo | None = None,
    ) -> None:
        self._song_repo = song_repo
        self._ffmpeg = ffmpeg
        self._demucs = demucs
        self._workspace = workspace
        self._task_repo = task_repo
        self._is_shutdown = is_shutdown
        self._separated_track_repo = separated_track_repo

    def execute(self, task: TaskInfo) -> None:
        """Run a Demucs source-separation task.  input_data: {"song_ids": [1,…]}."""
        try:
            from services.demucs_service import _execute_separation
        except ImportError:
            raise ToolExecutionError("Demucs execution not yet wired") from None

        input_data: dict = task.input_data or {}
        song_ids: list[int] = input_data.get("song_ids", [])
        model: str = input_data.get("model", "htdemucs")
        if not song_ids:
            logger.info("No song_ids in demucs task id=%d", task.id)
            self._task_repo.update_output(task.id, {"processed_song_ids": []})
            return

        processed_song_ids: list[int] = []
        total = len(song_ids)

        for i, song_id in enumerate(song_ids):
            if self._is_shutdown():
                logger.info(
                    "Shutdown — stopping demucs after %d/%d songs", i, total,
                )
                break
            try:
                song = self._song_repo.get_by_id(song_id)
            except Exception:
                logger.exception("Failed to load song id=%d", song_id)
                continue

            result_paths = _execute_separation(
                song, self._demucs, self._ffmpeg, self._workspace, model,
            )

            if self._separated_track_repo is not None:
                self._separated_track_repo.delete_by_song(song_id)
                self._separated_track_repo.insert(SeparatedTrack(
                    id=None,
                    song_id=song_id,
                    track_type="vocals",
                    file_path=result_paths["vocals_path"],
                ))
                self._separated_track_repo.insert(SeparatedTrack(
                    id=None,
                    song_id=song_id,
                    track_type="instrumental",
                    file_path=result_paths["inst_path"],
                ))

            song.has_vocal_removed = True
            try:
                self._song_repo.update(song)
            except Exception:
                logger.exception(
                    "Failed to update song id=%d after demucs", song_id,
                )

            processed_song_ids.append(song_id)

            progress = (i + 1) / total
            self._task_repo.update_status(
                task.id, TaskStatus.RUNNING, progress=progress,
            )
            task.progress = progress
            logger.info("Demucs %d/%d (%.0f%%)", i + 1, total, progress * 100)

        task.output_data = {"processed_song_ids": processed_song_ids}
        self._task_repo.update_output(task.id, task.output_data)

        if not processed_song_ids and song_ids:
            raise ToolExecutionError(
                f"All {len(song_ids)} demucs separation(s) failed",
            )
