"""Tests for playlists containing original and instrumental tracks."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models import Playlist, SeparatedTrack, Song
from services.playlist_service import PlaylistService


def _song(path: Path, title: str = "Test") -> Song:
    return Song(
        id=None,
        file_path=str(path),
        title=title,
        artist="Artist",
        album="Album",
        duration_ms=180_000,
        bitrate_bps=320_000,
        sample_rate_hz=44_100,
        channels=2,
        format="mp3",
        file_size_bytes=1,
    )


@pytest.fixture
def playlist_service(playlist_repo, song_repo, separated_track_repo, tmp_path):
    from services.config_service import ConfigService
    return PlaylistService(
        playlist_repo,
        song_repo,
        separated_track_repo,
        ConfigService(tmp_path / "config"),
    )


def test_playlist_keeps_original_and_instrumental_as_distinct_items(
    tmp_path, playlist_service, playlist_repo, song_repo, separated_track_repo
):
    song_file = tmp_path / "source.mp3"
    instrumental_file = tmp_path / "instrumental.mp3"
    song_file.touch()
    instrumental_file.touch()
    song = song_repo.insert(_song(song_file))
    track = separated_track_repo.insert(SeparatedTrack(
        id=None,
        song_id=song.id,
        track_type="instrumental",
        file_path=str(instrumental_file),
    ))
    playlist = playlist_repo.insert(Playlist(id=None, name="Morning"))

    playlist_service.add_songs(playlist.id, [song.id])
    assert playlist_service.add_instrumentals(playlist.id, [song.id]) == []

    loaded = playlist_service.get(playlist.id)
    assert len(loaded.items) == 2
    assert loaded.items[0].separated_track is None
    assert loaded.items[0].file_path == str(song_file)
    assert loaded.items[1].separated_track.id == track.id
    assert loaded.items[1].file_path == str(instrumental_file)
    assert loaded.items[1].title == "Test（伴奏）"

    playlist_service.reorder_items(
        playlist.id, [loaded.items[1].id, loaded.items[0].id]
    )
    playlist_service.remove_item(playlist.id, loaded.items[0].id)
    remaining = playlist_service.get(playlist.id).items
    assert len(remaining) == 1
    assert remaining[0].separated_track.id == track.id


def test_add_instrumentals_returns_songs_without_imported_track(
    tmp_path, playlist_service, playlist_repo, song_repo
):
    song = song_repo.insert(_song(tmp_path / "source.mp3"))
    playlist = playlist_repo.insert(Playlist(id=None, name="Morning"))

    assert playlist_service.add_instrumentals(playlist.id, [song.id]) == [song.id]
    assert playlist_service.get(playlist.id).items == []



def test_default_playlist_is_cleared_when_deleted(
    tmp_path, playlist_repo, song_repo, separated_track_repo
):
    from services.config_service import ConfigService

    config = ConfigService(tmp_path / "config")
    service = PlaylistService(playlist_repo, song_repo, separated_track_repo, config)
    playlist = service.create("Default")
    service.set_default_playlist(playlist.id)
    assert service.get_default_playlist_id() == playlist.id

    service.delete(playlist.id)
    assert service.get_default_playlist_id() is None
    assert config.get_default_playlist_id() is None


def test_playlist_export_validation_uses_instrumental_path(
    tmp_path, playlist_service, playlist_repo, song_repo, separated_track_repo
):
    song = song_repo.insert(_song(tmp_path / "source.mp3"))
    track = separated_track_repo.insert(SeparatedTrack(
        id=None,
        song_id=song.id,
        track_type="instrumental",
        file_path=str(tmp_path / "missing-instrumental.mp3"),
    ))
    playlist = playlist_repo.insert(Playlist(id=None, name="Morning"))
    playlist_service.add_instrumentals(playlist.id, [song.id])

    warnings = playlist_service.validate_export(playlist.id)
    assert str(track.file_path) in warnings[0]
