"""Tests for LibraryService — import, search, tags, delegation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.exceptions import SongNotFoundError
from core.models import Song
from database.song_repo import SongRepo
from services.library_service import LibraryService


class TestLibraryImport:
    """File import into the library."""

    def test_import_skips_unsupported_extension(self, library_service):
        assert library_service.import_files(["/tmp/test.txt"]) == []

    def test_import_skips_nonexistent_file(self, library_service):
        assert library_service.import_files(["/tmp/nonexistent_12345.mp3"]) == []

    def test_import_skips_duplicate_path(self, library_service, song_repo, mock_ffprobe):
        with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
            mock_ffprobe.probe.return_value = {
                "format": {
                    "duration": "180.5", "bit_rate": "320000",
                    "tags": {"title": "Test", "artist": "A", "album": "B"},
                },
                "streams": [{"codec_type": "audio", "sample_rate": "44100", "channels": "2"}],
            }
            result1 = library_service.import_files([f.name])
            assert len(result1) == 1
            result2 = library_service.import_files([f.name])
            assert len(result2) == 0

    def test_import_probes_and_creates_song(self, library_service, song_repo, mock_ffprobe):
        with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
            result = library_service.import_files([f.name])
            assert len(result) == 1
            song = result[0]
            assert song.title == "Test Song"
            assert song.artist == "Test Artist"
            assert song.duration_ms == 180500
            assert song.file_path == f.name

    def test_import_ncm_persists_decrypted_audio(
        self, tmp_path, song_repo, mock_ffprobe, ncm_decryptor, separated_track_repo
    ):
        from tools.ncm import NcmDecryptResult

        encrypted = tmp_path / "song.ncm"
        encrypted.touch()
        decrypted = tmp_path / "imported" / "ncm" / "song.mp3"
        decrypted.parent.mkdir(parents=True)
        decrypted.write_bytes(b"audio")
        ncm_decryptor.decrypt.return_value = NcmDecryptResult(
            file_path=str(decrypted), title="Decoded",
        )
        service = LibraryService(
            song_repo, mock_ffprobe, ncm_decryptor, tmp_path, separated_track_repo,
        )
        result = service.import_files([str(encrypted)])

        assert len(result) == 1
        song = result[0]
        assert song.source_file_path == str(encrypted.resolve())
        assert Path(song.file_path).is_file()
        assert Path(song.file_path).parent == tmp_path / "imported" / "ncm"
        assert ncm_decryptor.decrypt.called
        assert song_repo.get_by_source_path(str(encrypted.resolve())).id == song.id

    def test_ncm_import_skips_duplicate_source(
        self, tmp_path, song_repo, mock_ffprobe, ncm_decryptor, separated_track_repo
    ):
        from tools.ncm import NcmDecryptResult

        encrypted = tmp_path / "song.ncm"
        encrypted.touch()
        decrypted = tmp_path / "imported" / "ncm" / "song.mp3"
        decrypted.parent.mkdir(parents=True)
        decrypted.write_bytes(b"audio")
        ncm_decryptor.decrypt.return_value = NcmDecryptResult(file_path=str(decrypted))
        service = LibraryService(
            song_repo, mock_ffprobe, ncm_decryptor, tmp_path, separated_track_repo,
        )
        assert len(service.import_files([str(encrypted)])) == 1
        assert service.import_files([str(encrypted)]) == []

    def test_import_extension_list_includes_only_ncm_encryption(self, library_service):
        extensions = library_service.get_import_extensions()
        assert "ncm" in extensions
        assert "qmc2" not in extensions
        assert "kgm" not in extensions


class TestLibrarySearch:
    """Song search and filtering."""

    def test_search_by_title(self, library_service, song_repo):
        _insert_song(song_repo, file_path="/a.mp3", title="Hello World")
        _insert_song(song_repo, file_path="/b.mp3", title="Goodbye")
        results = library_service.search(query="Hello")
        assert len(results) == 1
        assert results[0].title == "Hello World"

    def test_search_by_artist(self, library_service, song_repo):
        _insert_song(song_repo, file_path="/a.mp3", title="Song1", artist="The Beatles")
        _insert_song(song_repo, file_path="/b.mp3", title="Song2", artist="Queen")
        results = library_service.search(query="Beatles")
        assert len(results) == 1

    def test_filter_by_format(self, library_service, song_repo):
        _insert_song(song_repo, file_path="/a.mp3", title="Mp3", format="mp3")
        _insert_song(song_repo, file_path="/b.flac", title="Flac", format="flac")
        results = library_service.search(format="flac")
        assert len(results) == 1
        assert results[0].title == "Flac"

    def test_filter_by_vocal_removed(self, library_service, song_repo):
        s1 = _insert_song(song_repo, file_path="/a.mp3", title="Normal")
        s2 = _insert_song(song_repo, file_path="/b.mp3", title="Removed")
        s2.has_vocal_removed = True
        song_repo.update(s2)
        results = library_service.search(has_vocal_removed=True)
        assert len(results) == 1
        assert results[0].title == "Removed"


class TestLibraryTags:
    """Tag management."""

    def test_add_and_get_tags(self, library_service, song_repo):
        song = _insert_song(song_repo, file_path="/a.mp3", title="Tagged")
        library_service.add_tag(song.id, "rock")
        library_service.add_tag(song.id, "live")
        tags = library_service.get_all_tags()
        assert len(tags) == 2
        assert {t.name for t in tags} == {"rock", "live"}

    def test_remove_tag(self, library_service, song_repo):
        song = _insert_song(song_repo, file_path="/a.mp3", title="Tagged")
        library_service.add_tag(song.id, "rock")
        library_service.remove_tag(song.id, "rock")
        tags = library_service.get_all_tags()
        # remove_tag only removes the song_tags junction, not the tag row
        assert len(tags) == 1


class TestLibraryCRUD:
    """Basic CRUD operations."""

    def test_get_song(self, library_service, song_repo):
        song = _insert_song(song_repo, file_path="/a.mp3", title="Get Me")
        fetched = library_service.get_song(song.id)
        assert fetched.title == "Get Me"

    def test_get_song_raises(self, library_service):
        with pytest.raises(SongNotFoundError):
            library_service.get_song(99999)

    def test_delete_song(self, library_service, song_repo):
        song = _insert_song(song_repo, file_path="/a.mp3", title="Delete Me")
        library_service.delete_song(song.id)
        with pytest.raises(SongNotFoundError):
            library_service.get_song(song.id)


class TestLibraryDelegation:
    """Separated track methods delegate to SeparatedTrackService."""

    def test_import_separated_tracks_delegates(self, library_service):
        with tempfile.TemporaryDirectory() as tmp:
            result = library_service.import_separated_tracks(tmp)
            assert result == {"matched": 0, "imported": 0, "skipped": 0}

    def test_get_separated_tracks_delegates(self, library_service):
        tracks = library_service.get_separated_tracks(1)
        assert tracks == []

    def test_get_separated_tracks_count_delegates(self, library_service):
        assert library_service.get_separated_tracks_count(1) == 0


def _insert_song(song_repo: SongRepo, *, file_path: str, title: str, artist: str = "Artist", format: str = "mp3") -> Song:
    return song_repo.insert(Song(
        id=None, file_path=file_path, title=title, artist=artist,
        album="Album", duration_ms=180000, bitrate_bps=320000,
        sample_rate_hz=44100, channels=2, format=format,
        file_size_bytes=5000000,
    ))
