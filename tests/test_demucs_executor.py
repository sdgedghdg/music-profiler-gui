"""Tests for Demucs result persistence."""

from __future__ import annotations

from pathlib import Path

from core.enums import TaskStatus, TaskType
from core.models import Song, TaskInfo
from database.task_repo import TaskRepo
from services.executors.demucs_executor import DemucsExecutor


def test_demucs_executor_replaces_separated_tracks(
    db_conn, song_repo, separated_track_repo, mock_ffmpeg, monkeypatch, tmp_path
):
    song = song_repo.insert(Song(
        id=None,
        file_path=str(tmp_path / "source.mp3"),
        title="Source",
        artist="Artist",
        album="Album",
        duration_ms=1,
        bitrate_bps=1,
        sample_rate_hz=1,
        channels=2,
        format="mp3",
        file_size_bytes=1,
    ))
    task = TaskRepo(db_conn).insert(TaskInfo(
        id=None,
        task_type=TaskType.DEMUCS,
        status=TaskStatus.PENDING,
        progress=0.0,
        input_data={"song_ids": [song.id]},
    ))
    monkeypatch.setattr(
        "services.demucs_service._execute_separation",
        lambda *_args: {"vocals_path": "/output/vocal.mp3", "inst_path": "/output/inst.mp3"},
    )

    executor = DemucsExecutor(
        song_repo,
        mock_ffmpeg,
        demucs=None,
        workspace=tmp_path,
        task_repo=TaskRepo(db_conn),
        is_shutdown=lambda: False,
        separated_track_repo=separated_track_repo,
    )
    executor.execute(task)

    tracks = separated_track_repo.get_by_song(song.id)
    assert {(track.track_type, track.file_path) for track in tracks} == {
        ("vocals", "/output/vocal.mp3"),
        ("instrumental", "/output/inst.mp3"),
    }
    assert song_repo.get_by_id(song.id).has_vocal_removed
