"""Export executor — broadcast file export."""

from __future__ import annotations

import logging
from pathlib import Path

from core.exceptions import ToolExecutionError
from core.models import ExportConfig, TaskInfo
from database.playlist_repo import PlaylistRepo
from database.task_repo import TaskRepo
from tools.ffmpeg import FFmpeg

logger = logging.getLogger(__name__)


class ExportExecutor:
    """Runs playlist export tasks.  All DB access through worker-owned repos."""

    def __init__(
        self,
        playlist_repo: PlaylistRepo,
        ffmpeg: FFmpeg,
        workspace: Path,
        task_repo: TaskRepo,
    ) -> None:
        self._playlist_repo = playlist_repo
        self._ffmpeg = ffmpeg
        self._workspace = workspace
        self._task_repo = task_repo

    def execute(self, task: TaskInfo) -> None:
        """Run an export task.  input_data: {"playlist_id": …, "config": {…}}."""
        from services.export_service import _execute_export as do_export

        input_data: dict = task.input_data or {}
        playlist_id: int = input_data.get("playlist_id")
        config_dict: dict = input_data.get("config", {})

        if playlist_id is None:
            raise ToolExecutionError("Export task missing playlist_id in input_data")

        config = ExportConfig(**config_dict)
        playlist = self._playlist_repo.get_by_id(playlist_id)
        output_path = do_export(playlist, config, self._ffmpeg, self._workspace)
        task.output_data = {"output_path": output_path}
        self._task_repo.update_output(task.id, task.output_data)
