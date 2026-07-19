"""Demucs service — vocal separation orchestration."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from core.enums import TaskStatus, TaskType
from core.models import Song, TaskInfo
from database.song_repo import SongRepo
from services.task_service import TaskService
from tools.demucs import Demucs
from tools.ffmpeg import FFmpeg, ProcessConfig

logger = logging.getLogger(__name__)


def _execute_separation(
    song: Song, demucs: Demucs, ffmpeg: FFmpeg, workspace: Path
) -> dict:
    """Run Demucs separation pipeline and return result paths."""
    with tempfile.TemporaryDirectory(prefix="musprof_demucs_") as tmpdir:
        tmpdir_path = Path(tmpdir)

        # 1. Run Demucs separation
        result = demucs.separate(song.file_path, tmpdir_path)
        stem_dir = Path(result.output_dir)

        # 2. Find non-vocal stems (everything except vocals.*)
        non_vocal_stems = sorted(
            str(p) for p in stem_dir.iterdir()
            if p.is_file() and not p.name.startswith("vocals.")
        )

        # 3. Merge non-vocal stems into inst.mp3
        inst_tmp = tmpdir_path / "inst.mp3"
        ffmpeg.merge_stems(non_vocal_stems, str(inst_tmp))

        # 4. Transcode vocals to vocal.mp3
        vocal_tmp = tmpdir_path / "vocal.mp3"
        mp3_config = ProcessConfig(output_format="mp3", bitrate_bps=320000)
        ffmpeg.transcode(result.vocals_path, str(vocal_tmp), mp3_config)

        # 5. Move results to workspace/demucs_output/
        output_dir = workspace / "demucs_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        song_stem = Path(song.file_path).stem
        final_vocal = output_dir / f"{song_stem}_vocal.mp3"
        final_inst = output_dir / f"{song_stem}_inst.mp3"

        shutil.move(str(vocal_tmp), str(final_vocal))
        shutil.move(str(inst_tmp), str(final_inst))

        logger.info(
            "Demucs separation complete for song %d: %s", song.id, song_stem
        )

        return {"vocals_path": str(final_vocal), "inst_path": str(final_inst)}


class DemucsService:
    """Service for vocal/accompaniment separation via Demucs."""

    def __init__(
        self,
        song_repo: SongRepo,
        task_service: TaskService,
        demucs: Demucs,
        ffmpeg: FFmpeg,
        workspace: Path,
    ) -> None:
        """Initialise with repositories, tools, and workspace root."""
        self._song_repo = song_repo
        self._task_service = task_service
        self._demucs = demucs
        self._ffmpeg = ffmpeg
        self._workspace = workspace

    def separate(self, song_ids: list[int]) -> TaskInfo:
        """Create and enqueue a vocal separation task."""
        for sid in song_ids:
            self._song_repo.get_by_id(sid)

        task = TaskInfo(
            id=None,
            task_type=TaskType.DEMUCS,
            status=TaskStatus.PENDING,
            progress=0.0,
            input_data={"song_ids": song_ids},
        )
        return self._task_service.enqueue(task)

    def get_result_paths(self, song: Song) -> dict[str, str] | None:
        """Return {vocals: path, inst: path} if processed, else None."""
        song_stem = Path(song.file_path).stem
        output_dir = self._workspace / "demucs_output"
        vocal_path = output_dir / f"{song_stem}_vocal.mp3"
        inst_path = output_dir / f"{song_stem}_inst.mp3"

        if vocal_path.exists() and inst_path.exists():
            return {"vocals": str(vocal_path), "inst": str(inst_path)}
        return None
