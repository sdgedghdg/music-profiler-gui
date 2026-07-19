"""Library service — import, search, metadata operations."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from core.models import AudioMetadata, SeparatedTrack, Song, Tag
from database.separated_track_repo import SeparatedTrackRepo
from database.song_repo import SongRepo
from services.separated_track_service import SeparatedTrackService
from tools.ffprobe import FFprobe
from tools.ncm import NcmDecryptor

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = frozenset({".mp3", ".flac", ".wav", ".m4a", ".ogg"})
_NCM_EXTENSION = ".ncm"
_IMPORT_EXTENSIONS = _SUPPORTED_EXTENSIONS | {_NCM_EXTENSION}


def _parse_ffprobe_output(data: dict, file_path: str) -> AudioMetadata:
    """Parse ffprobe JSON output into an AudioMetadata dataclass."""
    fmt = data.get("format", {})
    audio_stream = next(
        (stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"), {}
    )
    try:
        duration_ms = int(float(fmt.get("duration", "0")) * 1000)
    except (ValueError, TypeError):
        duration_ms = 0
    try:
        bitrate_bps = int(fmt.get("bit_rate", 0))
    except (ValueError, TypeError):
        bitrate_bps = 0
    try:
        sample_rate_hz = int(audio_stream.get("sample_rate", 0))
    except (ValueError, TypeError):
        sample_rate_hz = 0
    try:
        channels = int(audio_stream.get("channels", 2))
    except (ValueError, TypeError):
        channels = 2
    path = Path(file_path)
    tags = fmt.get("tags", {})
    return AudioMetadata(
        file_path=file_path,
        title=tags.get("title") or path.stem,
        artist=tags.get("artist", ""),
        album=tags.get("album", ""),
        duration_ms=duration_ms,
        bitrate_bps=bitrate_bps,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        format=path.suffix.lower().lstrip("."),
        file_size_bytes=path.stat().st_size,
    )


class LibraryService:
    """High-level operations for managing the audio library."""

    def __init__(
        self,
        song_repo: SongRepo,
        ffprobe: FFprobe,
        ncm_decryptor: NcmDecryptor,
        workspace: Path,
        separated_track_repo: SeparatedTrackRepo | None = None,
    ) -> None:
        self._song_repo = song_repo
        self._ffprobe = ffprobe
        self._ncm_decryptor = ncm_decryptor
        self._workspace = workspace
        self._separated_track_service = (
            SeparatedTrackService(song_repo, separated_track_repo)
            if separated_track_repo is not None else None
        )

    def import_files(self, file_paths: list[str]) -> list[Song]:
        """Import ordinary audio and decrypt NCM files to durable audio."""
        imported: list[Song] = []
        for raw_path in file_paths:
            source_path = Path(raw_path).resolve()
            if not source_path.is_file() or source_path.suffix.lower() not in _IMPORT_EXTENSIONS:
                logger.warning("Skipping unsupported input: %s", source_path)
                continue
            is_ncm = source_path.suffix.lower() == _NCM_EXTENSION
            if self._song_repo.get_by_path(str(source_path)) is not None:
                continue
            if is_ncm and self._song_repo.get_by_source_path(str(source_path)):
                continue

            playable_path = source_path
            ncm_metadata = None
            if is_ncm:
                output_dir = self._workspace / "imported" / "ncm"
                identifier = hashlib.sha256(str(source_path).encode()).hexdigest()[:12]
                result = self._ncm_decryptor.decrypt(source_path, output_dir)
                generated_path = Path(result.file_path)
                playable_path = generated_path.with_name(
                    f"{source_path.stem}_{identifier}{generated_path.suffix}"
                )
                if playable_path != generated_path:
                    generated_path.replace(playable_path)
                ncm_metadata = result

            try:
                metadata = _parse_ffprobe_output(
                    self._ffprobe.probe(str(playable_path)), str(playable_path)
                )
                song = Song(
                    id=None,
                    file_path=str(playable_path),
                    title=metadata.title or (ncm_metadata.title if ncm_metadata else ""),
                    artist=metadata.artist or (ncm_metadata.artist if ncm_metadata else ""),
                    album=metadata.album or (ncm_metadata.album if ncm_metadata else ""),
                    duration_ms=metadata.duration_ms,
                    bitrate_bps=metadata.bitrate_bps,
                    sample_rate_hz=metadata.sample_rate_hz,
                    channels=metadata.channels,
                    format=metadata.format,
                    file_size_bytes=metadata.file_size_bytes,
                    source_file_path=str(source_path) if is_ncm else None,
                )
                imported.append(self._song_repo.insert(song))
            except Exception:
                if is_ncm:
                    playable_path.unlink(missing_ok=True)
                raise
        return imported

    def get_song(self, song_id: int) -> Song:
        """Return a song by its id."""
        return self._song_repo.get_by_id(song_id)

    def search(self, **kwargs) -> list[Song]:
        """Search songs with optional filters."""
        return self._song_repo.search(**kwargs)

    def delete_song(self, song_id: int) -> None:
        """Delete a song from the library."""
        self._song_repo.delete(song_id)

    def add_tag(self, song_id: int, tag_name: str) -> None:
        """Add a tag to a song."""
        self._song_repo.add_tag(song_id, tag_name)

    def remove_tag(self, song_id: int, tag_name: str) -> None:
        """Remove a tag from a song."""
        self._song_repo.remove_tag(song_id, tag_name)

    def get_all_tags(self) -> list[Tag]:
        """Return all tags."""
        return self._song_repo.get_all_tags()

    def import_separated_tracks(self, folder_path: str) -> dict[str, int]:
        """Import separated tracks from a Demucs output folder."""
        if self._separated_track_service is None:
            raise RuntimeError("SeparatedTrackRepo is not configured")
        return self._separated_track_service.import_separated_tracks(folder_path)

    def get_separated_tracks(self, song_id: int) -> list[SeparatedTrack]:
        """Return all separated tracks for a song."""
        if self._separated_track_service is None:
            return []
        return self._separated_track_service.get_separated_tracks(song_id)

    def get_separated_tracks_count(self, song_id: int) -> int:
        """Return the number of separated tracks for a song."""
        return len(self.get_separated_tracks(song_id))

    @staticmethod
    def get_supported_formats() -> list[str]:
        """Return actual library audio formats."""
        return [extension.lstrip(".") for extension in sorted(_SUPPORTED_EXTENSIONS)]

    @staticmethod
    def get_import_extensions() -> list[str]:
        """Return ordinary audio formats plus NCM."""
        return [extension.lstrip(".") for extension in sorted(_IMPORT_EXTENSIONS)]
