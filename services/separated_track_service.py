"""Separated track service — import and query separated audio tracks."""

from __future__ import annotations

import logging
from pathlib import Path

from core.models import SeparatedTrack
from database.separated_track_repo import SeparatedTrackRepo
from database.song_repo import SongRepo

logger = logging.getLogger(__name__)


class SeparatedTrackService:
    """Operations for importing and querying separated audio tracks."""

    _TRACK_TYPE_MAP: dict[str, str] = {
        "vocals": "vocals", "vocal": "vocals",
        "no_vocals": "instrumental", "inst": "instrumental",
        "instrumental": "instrumental",
        "drums": "drums", "bass": "bass",
    }

    _TRACK_SUFFIXES: tuple[str, ...] = (
        "_no_vocals", "_instrumental",
        "_vocals", "_vocal", "_inst",
        "_drums", "_bass", "_other",
    )

    def __init__(
        self,
        song_repo: SongRepo,
        separated_track_repo: SeparatedTrackRepo,
    ) -> None:
        self._song_repo = song_repo
        self._separated_track_repo = separated_track_repo

    @classmethod
    def _map_track_type(cls, name: str) -> str:
        """Map a raw track name (e.g. 'vocals', 'no_vocals') to a standard type."""
        return cls._TRACK_TYPE_MAP.get(name.lower(), "other")

    @classmethod
    def _classify_our_file(cls, file_path: Path) -> tuple[str, str] | None:
        """Try to classify a file in our processed format.

        Returns ``(base_stem, track_type)`` or ``None`` if the filename
        doesn't match a recognised pattern.
        """
        stem = file_path.stem
        stem_lower = stem.lower()
        if stem_lower in {"vocals", "vocal", "no_vocals", "instrumental", "inst", "drums", "bass", "other"}:
            return None
        for suffix in cls._TRACK_SUFFIXES:
            if stem_lower.endswith(suffix) and len(stem) >= len(suffix):
                base = stem[:-len(suffix)]
                if not base:
                    return None
                track_type = cls._map_track_type(suffix.lstrip("_"))
                return base, track_type
        return None

    def _match_songs(self, stems: list[str]) -> dict[str, int]:
        """Match filename stems to song IDs.

        Returns a dict mapping each *original* stem to a ``song_id``.
        Stems that cannot be matched are omitted.
        """
        all_songs = self._song_repo.search(limit=100_000)

        # Pre-build lookup maps for efficient matching
        exact_map: dict[str, int] = {}    # Path.stem          -> song_id
        lower_map: dict[str, int] = {}    # Path.stem.lower()  -> song_id
        for song in all_songs:
            song_stem = Path(song.file_path).stem
            exact_map[song_stem] = song.id
            lower_map[song_stem.lower()] = song.id

        matched: dict[str, int] = {}
        suffixes = self._TRACK_SUFFIXES

        for stem in stems:
            # 1. Exact match
            if stem in exact_map:
                matched[stem] = exact_map[stem]
                continue

            # 2. Case-insensitive match
            stem_lower = stem.lower()
            if stem_lower in lower_map:
                matched[stem] = lower_map[stem_lower]
                continue

            # 3. Try stripping common track-type suffixes
            for suffix in suffixes:
                if stem_lower.endswith(suffix) and len(stem) > len(suffix):
                    base = stem[:-len(suffix)]
                    if base in exact_map:
                        matched[stem] = exact_map[base]
                        break
                    base_lower = base.lower()
                    if base_lower in lower_map:
                        matched[stem] = lower_map[base_lower]
                        break

        return matched

    def import_separated_tracks(self, folder_path: str) -> dict[str, int]:
        """Scan a folder for separated audio tracks and link them to songs.

        Supports two structures:

        1. Our processed format
           ``{song_stem}_vocal.mp3``, ``{song_stem}_inst.mp3``, ...

        2. Raw Demucs format
           ``{model_name}/{song_name}/vocals.wav``, ``no_vocals.wav``, ...

        Returns ``{"matched": N, "imported": N, "skipped": N}``.
        """
        logger.info("Importing separated tracks from %r", folder_path)

        folder = Path(folder_path)
        if not folder.is_dir():
            raise ValueError(f"Not a directory: {folder_path}")

        # Recursively collect audio files
        audio_files: list[Path] = []
        for ext in (".mp3", ".wav", ".flac"):
            audio_files.extend(folder.rglob(f"*{ext}"))

        if not audio_files:
            logger.info("No audio files found in %s", folder_path)
            return {"matched": 0, "imported": 0, "skipped": 0}

        # Detect format: are any filenames in our processed naming pattern?
        our_files: list[tuple[Path, str, str]] = []  # (path, base_stem, track_type)
        for f in audio_files:
            classified = self._classify_our_file(f)
            if classified is not None:
                our_files.append((f, classified[0], classified[1]))

        if our_files:
            logger.debug("Detected processed format — %d classified files",
                         len(our_files))
            return self._import_our_format(our_files)
        else:
            logger.debug("Detected raw Demucs format — %d files", len(audio_files))
            return self._import_demucs_format(folder, audio_files)

    def _import_our_format(
        self, classified: list[tuple[Path, str, str]],
    ) -> dict[str, int]:
        """Import tracks from our processed naming convention."""
        # Group by base stem
        groups: dict[str, list[tuple[Path, str]]] = {}
        for file_path, base_stem, track_type in classified:
            groups.setdefault(base_stem, []).append((file_path, track_type))

        stems = list(groups.keys())
        stem_to_song = self._match_songs(stems)

        matched = 0
        imported = 0
        skipped = 0

        for base_stem, files in groups.items():
            song_id = stem_to_song.get(base_stem)
            if song_id is None:
                logger.debug("No song match for stem %r", base_stem)
                continue
            matched += 1

            imported_before = imported
            skipped_before = skipped
            for file_path, track_type in files:
                existing = self._separated_track_repo.get_by_type(
                    song_id, track_type,
                )
                if existing is not None:
                    logger.debug("Track type %r already exists for song %d, skipping",
                                 track_type, song_id)
                    skipped += 1
                    continue

                track = SeparatedTrack(
                    id=None, song_id=song_id, track_type=track_type,
                    file_path=str(file_path),
                )
                self._separated_track_repo.insert(track)
                imported += 1
                logger.info("Imported %s track for song %d: %s",
                           track_type, song_id, file_path)

            if imported > imported_before or skipped > skipped_before:
                song = self._song_repo.get_by_id(song_id)
                if not song.has_vocal_removed:
                    song.has_vocal_removed = True
                    self._song_repo.update(song)

        return {"matched": matched, "imported": imported, "skipped": skipped}

    def _import_demucs_format(
        self, folder: Path, audio_files: list[Path],
    ) -> dict[str, int]:
        """Import tracks from raw Demucs directory structure."""
        # Group files by their immediate parent directory (the song folder)
        dir_groups: dict[Path, list[Path]] = {}
        for f in audio_files:
            if f.parent == folder:
                continue  # skip files directly in the root
            dir_groups.setdefault(f.parent, []).append(f)

        if not dir_groups:
            logger.info("No subdirectories with audio files found")
            return {"matched": 0, "imported": 0, "skipped": 0}

        stems = [d.name for d in dir_groups.keys()]
        stem_to_song = self._match_songs(stems)

        matched = 0
        imported = 0
        skipped = 0

        for song_dir, files in dir_groups.items():
            stem = song_dir.name
            song_id = stem_to_song.get(stem)
            if song_id is None:
                logger.debug("No song match for directory %r", stem)
                continue
            matched += 1

            for file_path in files:
                track_type = self._map_track_type(file_path.stem)
                existing = self._separated_track_repo.get_by_type(
                    song_id, track_type,
                )
                if existing is not None:
                    logger.debug("Track type %r already exists for song %d, skipping",
                                 track_type, song_id)
                    skipped += 1
                    continue

                track = SeparatedTrack(
                    id=None, song_id=song_id, track_type=track_type,
                    file_path=str(file_path),
                )
                self._separated_track_repo.insert(track)
                imported += 1
                logger.info("Imported %s track for song %d: %s",
                           track_type, song_id, file_path)

            if imported > 0 or skipped > 0:
                song = self._song_repo.get_by_id(song_id)
                if not song.has_vocal_removed:
                    song.has_vocal_removed = True
                    self._song_repo.update(song)

        return {"matched": matched, "imported": imported, "skipped": skipped}

    def get_separated_tracks(self, song_id: int) -> list[SeparatedTrack]:
        """Return all separated tracks for a song."""
        return self._separated_track_repo.get_by_song(song_id)

    def get_separated_tracks_count(self, song_id: int) -> int:
        """Return the number of separated tracks for a song."""
        return len(self._separated_track_repo.get_by_song(song_id))

    def get_track_counts(self, song_ids: list[int]) -> dict[int, int]:
        """Return ``{song_id: track_count}`` for many songs in one query batch."""
        if not song_ids:
            return {}
        return self._separated_track_repo.count_by_song_ids(song_ids)
