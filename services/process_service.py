"""Audio processing service — batch task creation."""

from __future__ import annotations

import logging

from core.exceptions import SongNotFoundError
from core.models import ProcessConfig, TaskInfo
from database.song_repo import SongRepo
from services.task_service import TaskService

logger = logging.getLogger(__name__)


class ProcessService:
    """Service for creating batch audio processing tasks."""

    def __init__(self, song_repo: SongRepo, task_service: TaskService) -> None:
        """Initialise with song repository and task service."""
        self._song_repo = song_repo
        self._task_service = task_service

    def transcode_batch(
        self, song_ids: list[int], config: ProcessConfig
    ) -> TaskInfo:
        """Create and enqueue a batch transcode task."""
        self._validate_song_ids(song_ids)
        task = TaskInfo(
            id=None,
            task_type="transcode",
            status="pending",
            progress=0.0,
            input_data={
                "song_ids": song_ids,
                "config": config.__dict__,
            },
        )
        return self._task_service.enqueue(task)

    def normalize_loudness_batch(
        self, song_ids: list[int], target_lufs: float = -16.0
    ) -> TaskInfo:
        """Create and enqueue a batch loudness normalisation task."""
        self._validate_song_ids(song_ids)
        config = ProcessConfig(target_loudness_lufs=target_lufs)
        task = TaskInfo(
            id=None,
            task_type="transcode",
            status="pending",
            progress=0.0,
            input_data={
                "song_ids": song_ids,
                "config": config.__dict__,
            },
        )
        return self._task_service.enqueue(task)

    def _validate_song_ids(self, song_ids: list[int]) -> None:
        """Raise SongNotFoundError if any song_ids do not exist."""
        bad_ids: list[int] = []
        for sid in song_ids:
            try:
                self._song_repo.get_by_id(sid)
            except SongNotFoundError:
                bad_ids.append(sid)
        if bad_ids:
            raise SongNotFoundError(
                f"Songs not found: {', '.join(str(i) for i in bad_ids)}"
            )
