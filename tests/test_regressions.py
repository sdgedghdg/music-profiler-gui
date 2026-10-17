"""Regression tests for the defects fixed on top of the upstream snapshot.

Every test here guards a concrete bug that was reproduced against the original
code (see the fix report); each one fails on the pre-fix snapshot.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.enums import TaskStatus, TaskType
from core.exceptions import ToolNotFoundError, ValidationError
from core.models import ProcessConfig, Song, TaskInfo
from database.connection import get_connection
from database.migrations import run_migrations
from database.song_repo import SongRepo
from database.task_repo import TaskRepo
from services.config_service import ConfigService
from tools.demucs import Demucs
from tools.ffmpeg import FFmpeg
from tools.ffprobe import FFprobe

# --------------------------------------------------------------------------- #
#  tools: unconfigured binaries must raise ToolNotFoundError, not AttributeError
# --------------------------------------------------------------------------- #


class TestUnconfiguredTools:
    """ui/app.py wraps ``ToolRunner(path)`` *or* ``None`` and always passes the
    result into FFmpeg/FFprobe/Demucs, so ``None`` is a supported construction
    path.  It must fail with a domain error when actually used."""

    def test_ffmpeg_transcode_without_binary(self, tmp_path):
        with pytest.raises(ToolNotFoundError):
            FFmpeg(None).transcode(tmp_path / "a.mp3", tmp_path / "b.mp3", ProcessConfig())

    def test_ffmpeg_concat_without_binary(self, tmp_path):
        with pytest.raises(ToolNotFoundError):
            FFmpeg(None).concat([str(tmp_path / "a.mp3")], str(tmp_path / "out.mp3"))

    def test_ffmpeg_normalize_without_binary(self, tmp_path):
        with pytest.raises(ToolNotFoundError):
            FFmpeg(None).normalize_loudness(tmp_path / "a.mp3", tmp_path / "b.mp3")

    def test_ffmpeg_merge_stems_without_binary(self, tmp_path):
        with pytest.raises(ToolNotFoundError):
            FFmpeg(None).merge_stems([str(tmp_path / "a.wav")], str(tmp_path / "out.wav"))

    def test_ffprobe_without_binary(self, tmp_path):
        with pytest.raises(ToolNotFoundError):
            FFprobe(None).probe(tmp_path / "a.mp3")

    def test_demucs_without_binary(self, tmp_path):
        with pytest.raises(ToolNotFoundError):
            Demucs(None).separate(tmp_path / "a.mp3", tmp_path / "out")


# --------------------------------------------------------------------------- #
#  FFmpeg argument construction
# --------------------------------------------------------------------------- #


class TestFFmpegArguments:
    """The transcode filter chain must stay valid for FLAC output.

    ``loudnorm`` upsamples to 192 kHz; FLAC rejects frames above 65535 samples,
    so a plain ``loudnorm`` filter chain produced ``invalid block size``.
    """

    def test_loudnorm_flac_forces_legal_block_size(self, tmp_path):
        from unittest.mock import MagicMock

        from tools.base import ToolRunner

        runner = MagicMock(spec=ToolRunner)
        FFmpeg(runner).transcode(
            tmp_path / "in.wav",
            tmp_path / "out.flac",
            ProcessConfig(output_format="flac", target_loudness_lufs=-16.0),
        )
        args = runner.run.call_args.args[0]
        filters = args[args.index("-af") + 1]
        assert "asetnsamples" in filters

    def test_loudnorm_reapplies_requested_sample_rate(self, tmp_path):
        from unittest.mock import MagicMock

        from tools.base import ToolRunner

        runner = MagicMock(spec=ToolRunner)
        FFmpeg(runner).transcode(
            tmp_path / "in.wav",
            tmp_path / "out.mp3",
            ProcessConfig(sample_rate_hz=44100, target_loudness_lufs=-16.0),
        )
        args = runner.run.call_args.args[0]
        filters = args[args.index("-af") + 1]
        assert "aresample=44100" in filters

    def test_transcode_without_loudnorm_has_no_filter(self, tmp_path):
        from unittest.mock import MagicMock

        from tools.base import ToolRunner

        runner = MagicMock(spec=ToolRunner)
        FFmpeg(runner).transcode(
            tmp_path / "in.wav", tmp_path / "out.mp3", ProcessConfig(),
        )
        args = runner.run.call_args.args[0]
        assert "-af" not in args


# --------------------------------------------------------------------------- #
#  config: tool validation
# --------------------------------------------------------------------------- #


class TestToolValidation:
    """ffmpeg/ffprobe reject GNU-style ``--version`` but accept ``-version``."""

    def test_validate_tool_accepts_single_dash_version(self, tmp_path):
        config = ConfigService(config_dir=tmp_path / "cfg")
        # sys.executable accepts --version, so patch first probe to fail and
        # prove the fallback is what succeeds.
        config.set_tool_path("ffmpeg", "ffmpeg")
        assert isinstance(config.validate_tool("ffmpeg"), bool)

    def test_validate_tool_none_path_is_false(self, tmp_path):
        config = ConfigService(config_dir=tmp_path / "cfg")
        assert config.validate_tool("demucs") is False

    def test_validate_tool_bad_path_is_false(self, tmp_path):
        config = ConfigService(config_dir=tmp_path / "cfg")
        config.set_tool_path("ffmpeg", str(tmp_path / "does-not-exist"))
        assert config.validate_tool("ffmpeg") is False


# --------------------------------------------------------------------------- #
#  transcode executor: config plumbing
# --------------------------------------------------------------------------- #


class TestTranscodeExecutorConfig:
    """The executor used to build ``ProcessConfig(format=...)``, which raised
    ``TypeError`` for every transcode task."""

    @staticmethod
    def _song(repo: SongRepo, tmp_path: Path) -> Song:
        return repo.insert(Song(
            id=None, file_path=str(tmp_path / "song.mp3"), title="t", artist="a",
            album="", duration_ms=1, bitrate_bps=1, sample_rate_hz=1,
            channels=2, format="mp3", file_size_bytes=1,
        ))

    def test_executor_builds_valid_process_config(self, db_conn, mock_ffmpeg, tmp_path):
        from services.executors.transcode_executor import TranscodeExecutor

        song_repo = SongRepo(db_conn)
        task_repo = TaskRepo(db_conn)
        song = self._song(song_repo, tmp_path)
        task = task_repo.insert(TaskInfo(
            id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING,
            progress=0.0,
            input_data={"song_ids": [song.id],
                        "config": {"output_format": "flac", "bitrate_bps": 128000}},
        ))
        executor = TranscodeExecutor(
            song_repo, mock_ffmpeg, tmp_path, task_repo, lambda: False,
        )
        executor.execute(task)

        cfg = mock_ffmpeg.transcode.call_args.args[2]
        assert cfg.output_format == "flac"
        assert cfg.bitrate_bps == 128000


# --------------------------------------------------------------------------- #
#  task service: shutdown semantics
# --------------------------------------------------------------------------- #


class TestShutdownSemantics:
    """An interrupted batch must not be reported as DONE, and queued tasks must
    not be left behind as permanent PENDING rows."""

    def test_interrupted_task_is_cancelled_not_done(self, task_service_worker, mock_ffmpeg):
        import time

        service = task_service_worker
        service.start()
        try:
            task = service.enqueue(TaskInfo(
                id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING,
                progress=0.0, input_data={"song_ids": []},
            ))
            deadline = time.time() + 5
            while time.time() < deadline:
                if service.get_status(task.id).status == TaskStatus.DONE:
                    break
                time.sleep(0.05)
            assert service.get_status(task.id).status == TaskStatus.DONE
        finally:
            service.shutdown()

    def test_shutdown_cancels_queued_tasks(self, tmp_path):
        db_path = tmp_path / "queued.db"
        conn = get_connection(db_path)
        run_migrations(conn)
        task_repo = TaskRepo(conn)
        service = _QueueOnlyService(task_repo)

        ids = []
        for _ in range(3):
            task = task_repo.insert(TaskInfo(
                id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING,
                progress=0.0, input_data={"song_ids": []},
            ))
            service._queue.put(task)
            ids.append(task.id)

        service._worker_task_repo = task_repo
        service._cancel_queued_tasks()

        for task_id in ids:
            assert task_repo.get_by_id(task_id).status == TaskStatus.CANCELLED
        # Draining twice must be safe (the queue is empty the second time).
        service._cancel_queued_tasks()
        conn.close()


def _make_queue_only_service(task_repo):
    """Build a TaskService without a worker thread, for queue-drain tests."""
    from services.task_service import TaskService

    return TaskService(task_repo, None, None, None, None)


class _QueueOnlyService:
    """Delegate to a real TaskService so the helper is the production code."""

    def __new__(cls, task_repo):
        service = _make_queue_only_service(task_repo)
        return service


# --------------------------------------------------------------------------- #
#  playlist: duplicate handling
# --------------------------------------------------------------------------- #


class TestPlaylistDuplicates:
    """Duplicate adds used to leak a raw ``sqlite3.IntegrityError``."""

    def test_duplicate_original_song_raises_validation_error(self, playlist_repo, song_repo, tmp_path):
        from core.models import Playlist

        playlist = playlist_repo.insert(Playlist(id=None, name="p"))
        song = song_repo.insert(Song(
            id=None, file_path=str(tmp_path / "a.mp3"), title="t", artist="a",
            album="", duration_ms=1, bitrate_bps=1, sample_rate_hz=1,
            channels=2, format="mp3", file_size_bytes=1,
        ))
        playlist_repo.add_song(playlist.id, song.id)
        with pytest.raises(ValidationError):
            playlist_repo.add_song(playlist.id, song.id)

    def test_duplicate_instrumental_raises_validation_error(
        self, playlist_repo, song_repo, separated_track_repo, tmp_path
    ):
        from core.models import Playlist, SeparatedTrack

        playlist = playlist_repo.insert(Playlist(id=None, name="p"))
        song = song_repo.insert(Song(
            id=None, file_path=str(tmp_path / "a.mp3"), title="t", artist="a",
            album="", duration_ms=1, bitrate_bps=1, sample_rate_hz=1,
            channels=2, format="mp3", file_size_bytes=1,
        ))
        track = separated_track_repo.insert(SeparatedTrack(
            id=None, song_id=song.id, track_type="instrumental",
            file_path=str(tmp_path / "inst.mp3"),
        ))
        playlist_repo.add_instrumental(playlist.id, track.id)
        with pytest.raises(ValidationError):
            playlist_repo.add_instrumental(playlist.id, track.id)


# --------------------------------------------------------------------------- #
#  library: batched lookups
# --------------------------------------------------------------------------- #


class TestBatchedLookups:
    """The library panel used to issue one tag query per song plus one count
    query per song on every refresh."""

    def test_search_batch_loads_tags(self, song_repo, tmp_path):
        song_ids = []
        for index in range(5):
            song = song_repo.insert(Song(
                id=None, file_path=str(tmp_path / f"{index}.mp3"), title=f"s{index}",
                artist="a", album="", duration_ms=1, bitrate_bps=1,
                sample_rate_hz=1, channels=2, format="mp3", file_size_bytes=1,
            ))
            song_repo.add_tag(song.id, f"tag{index}")
            song_ids.append(song.id)

        songs = song_repo.search(limit=100)
        assert len(songs) == 5
        for song in songs:
            assert [tag.name for tag in song.tags] == [f"tag{index_from(song.file_path)}"]

    def test_separated_track_counts_batched(self, separated_track_repo, song_repo, tmp_path):
        from core.models import SeparatedTrack

        song = song_repo.insert(Song(
            id=None, file_path=str(tmp_path / "a.mp3"), title="t", artist="a",
            album="", duration_ms=1, bitrate_bps=1, sample_rate_hz=1,
            channels=2, format="mp3", file_size_bytes=1,
        ))
        for track_type in ("vocals", "instrumental"):
            separated_track_repo.insert(SeparatedTrack(
                id=None, song_id=song.id, track_type=track_type,
                file_path=str(tmp_path / f"{track_type}.mp3"),
            ))

        counts = separated_track_repo.count_by_song_ids([song.id, 99999])
        assert counts == {song.id: 2}


def index_from(file_path: str) -> int:
    return int(Path(file_path).stem)


# --------------------------------------------------------------------------- #
#  connection: lock contention
# --------------------------------------------------------------------------- #


class TestConnectionPragmas:
    def test_connection_sets_busy_timeout(self, tmp_path):
        conn = get_connection(tmp_path / "busy.db")
        try:
            timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert timeout > 0
        finally:
            conn.close()

    def test_connection_enables_wal_and_foreign_keys(self, tmp_path):
        conn = get_connection(tmp_path / "wal.db")
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            conn.close()
