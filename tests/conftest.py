"""Shared test fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from database.migrations import run_migrations
from database.playlist_repo import PlaylistRepo
from database.separated_track_repo import SeparatedTrackRepo
from database.song_repo import SongRepo
from database.task_repo import TaskRepo
from services.library_service import LibraryService
from services.separated_track_service import SeparatedTrackService
from services.task_service import TaskService
from tools.ffmpeg import FFmpeg
from tools.ffprobe import FFprobe
from tools.ncm import NcmDecryptor


@pytest.fixture
def db_conn():
    """In-memory SQLite connection with full schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def song_repo(db_conn):
    return SongRepo(db_conn)


@pytest.fixture
def task_repo(db_conn):
    return TaskRepo(db_conn)


@pytest.fixture
def playlist_repo(db_conn):
    return PlaylistRepo(db_conn)


@pytest.fixture
def separated_track_repo(db_conn):
    return SeparatedTrackRepo(db_conn)


@pytest.fixture
def mock_ffmpeg():
    return MagicMock(spec=FFmpeg)


@pytest.fixture
def mock_ffprobe():
    ffprobe = MagicMock(spec=FFprobe)
    ffprobe.probe.return_value = {
        "format": {
            "duration": "180.5",
            "bit_rate": "320000",
            "tags": {"title": "Test Song", "artist": "Test Artist", "album": "Test Album"},
        },
        "streams": [{"codec_type": "audio", "sample_rate": "44100", "channels": "2"}],
    }
    return ffprobe


@pytest.fixture
def ncm_decryptor():
    return MagicMock(spec=NcmDecryptor)


@pytest.fixture
def library_service(song_repo, mock_ffprobe, ncm_decryptor, separated_track_repo):
    workspace = Path("/tmp/test_workspace")
    return LibraryService(song_repo, mock_ffprobe, ncm_decryptor, workspace, separated_track_repo)


@pytest.fixture
def separated_track_service(song_repo, separated_track_repo):
    return SeparatedTrackService(song_repo, separated_track_repo)


@pytest.fixture
def task_service(task_repo, song_repo, playlist_repo, mock_ffmpeg):
    """TaskService without worker thread support — for enqueue/cancel/query tests."""
    service = TaskService(
        task_repo,
        song_repo,
        mock_ffmpeg,
        demucs=None,
        workspace=Path("/tmp/test_workspace"),
        playlist_repo=playlist_repo,
        separated_track_repo=separated_track_repo,
    )
    yield service
    service.shutdown()


def _init_file_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    run_migrations(conn)
    return conn


@pytest.fixture
def task_service_worker(tmp_path, mock_ffmpeg):
    """TaskService with file-based DB — worker thread creates its own connections."""
    db_path = str(tmp_path / "test_worker.db")
    _init_file_db(db_path).close()

    def _new_conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    main_conn = _new_conn()
    try:
        service = TaskService(
            TaskRepo(main_conn),
            SongRepo(main_conn),
            mock_ffmpeg,
            demucs=None,
            workspace=tmp_path,
            playlist_repo=PlaylistRepo(main_conn),
            separated_track_repo=SeparatedTrackRepo(main_conn),
            db_factory=_new_conn,
        )
        yield service
    finally:
        service.shutdown()
        main_conn.close()
