"""Tests for SeparatedTrackService — track classification, import, and matching."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.models import Song
from database.song_repo import SongRepo


class TestSeparatedTrackClassification:
    """File classification and naming."""

    def test_classify_vocal_file(self, separated_track_service):
        result = separated_track_service._classify_our_file(Path("song1_vocal.mp3"))
        assert result is not None
        base, track_type = result
        assert base == "song1"
        assert track_type == "vocals"

    def test_classify_inst_file(self, separated_track_service):
        result = separated_track_service._classify_our_file(Path("song1_inst.mp3"))
        assert result is not None
        base, track_type = result
        assert base == "song1"
        assert track_type == "instrumental"

    def test_classify_instrumental_file(self, separated_track_service):
        result = separated_track_service._classify_our_file(Path("song1_instrumental.mp3"))
        assert result is not None
        assert result[1] == "instrumental"

    def test_classify_no_vocals_file(self, separated_track_service):
        result = separated_track_service._classify_our_file(Path("song1_no_vocals.wav"))
        assert result is not None
        assert result[1] == "instrumental"

    def test_classify_unknown_stem_returns_other(self, separated_track_service):
        assert separated_track_service._map_track_type("drums") == "drums"
        assert separated_track_service._map_track_type("bass") == "bass"
        assert separated_track_service._map_track_type("unknown_suffix") == "other"

    def test_classify_unrelated_file_returns_none(self, separated_track_service):
        assert separated_track_service._classify_our_file(Path("song1.mp3")) is None
        assert separated_track_service._classify_our_file(Path("song1.wav")) is None


class TestSongMatching:
    """Matching filename stems to song IDs."""

    def test_exact_match(self, song_repo, separated_track_service):
        song = _insert_song(song_repo, file_path="/music/My Song.mp3", title="My Song")
        matched = separated_track_service._match_songs(["My Song"])
        assert matched.get("My Song") == song.id

    def test_case_insensitive_match(self, song_repo, separated_track_service):
        song = _insert_song(song_repo, file_path="/music/my song.mp3", title="My Song")
        matched = separated_track_service._match_songs(["MY SONG"])
        assert matched.get("MY SONG") == song.id

    def test_suffix_stripping_match(self, song_repo, separated_track_service):
        song = _insert_song(song_repo, file_path="/music/My Song.mp3", title="My Song")
        matched = separated_track_service._match_songs(["My Song_vocal"])
        assert matched.get("My Song_vocal") == song.id

    def test_no_match_returns_empty(self, song_repo, separated_track_service):
        matched = separated_track_service._match_songs(["Nonexistent"])
        assert "Nonexistent" not in matched


class TestImportSeparatedTracks:
    """End-to-end import of separated tracks."""

    def test_import_empty_folder(self, separated_track_service):
        with tempfile.TemporaryDirectory() as tmp:
            result = separated_track_service.import_separated_tracks(tmp)
            assert result == {"matched": 0, "imported": 0, "skipped": 0}

    def test_import_our_format(self, song_repo, separated_track_repo, separated_track_service):
        song = _insert_song(song_repo, file_path="/music/Test.mp3", title="Test")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Test_vocal.mp3").touch()
            (Path(tmp) / "Test_inst.mp3").touch()
            result = separated_track_service.import_separated_tracks(tmp)
            assert result["matched"] == 1
            assert result["imported"] == 2
            tracks = separated_track_service.get_separated_tracks(song.id)
            assert len(tracks) == 2

    def test_import_demucs_format(self, song_repo, separated_track_repo, separated_track_service):
        song = _insert_song(song_repo, file_path="/music/Test.mp3", title="Test")
        with tempfile.TemporaryDirectory() as tmp:
            song_dir = Path(tmp) / "Test"
            song_dir.mkdir()
            (song_dir / "vocals.wav").touch()
            (song_dir / "no_vocals.wav").touch()
            result = separated_track_service.import_separated_tracks(tmp)
            assert result["matched"] == 1
            assert result["imported"] == 2

    def test_import_skips_duplicate_tracks(self, song_repo, separated_track_repo, separated_track_service):
        song = _insert_song(song_repo, file_path="/music/Test.mp3", title="Test")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Test_vocal.mp3").touch()
            # First import
            separated_track_service.import_separated_tracks(tmp)
            # Second import should skip
            (Path(tmp) / "Test_vocal.mp3").touch()
            result = separated_track_service.import_separated_tracks(tmp)
            assert result["skipped"] >= 1

    def test_get_separated_tracks_count(self, song_repo, separated_track_repo, separated_track_service):
        song = _insert_song(song_repo, file_path="/music/Test.mp3", title="Test")
        assert separated_track_service.get_separated_tracks_count(song.id) == 0
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Test_vocal.mp3").touch()
            separated_track_service.import_separated_tracks(tmp)
            assert separated_track_service.get_separated_tracks_count(song.id) == 1


def _insert_song(song_repo: SongRepo, *, file_path: str, title: str) -> Song:
    return song_repo.insert(Song(
        id=None, file_path=file_path, title=title, artist="Artist",
        album="Album", duration_ms=180000, bitrate_bps=320000,
        sample_rate_hz=44100, channels=2, format="mp3",
        file_size_bytes=5000000,
    ))
