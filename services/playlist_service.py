"""Playlist service — CRUD, item management, stats, export validation."""

from __future__ import annotations

import logging
from pathlib import Path

from core.exceptions import PlaylistNotFoundError, ValidationError
from core.models import Playlist, PlaylistStats
from database.playlist_repo import PlaylistRepo
from database.separated_track_repo import SeparatedTrackRepo
from database.song_repo import SongRepo
from services.config_service import ConfigService

logger = logging.getLogger(__name__)


class PlaylistService:
    """Business logic for playlist management."""

    def __init__(
        self,
        playlist_repo: PlaylistRepo,
        song_repo: SongRepo,
        separated_track_repo: SeparatedTrackRepo,
        config_service: ConfigService,
    ) -> None:
        self._playlist_repo = playlist_repo
        self._song_repo = song_repo
        self._separated_track_repo = separated_track_repo
        self._config_service = config_service

    def create(self, name: str, description: str = "") -> Playlist:
        """Create a new playlist; *name* must not be empty."""
        name = name.strip()
        if not name:
            raise ValidationError("Playlist name must not be empty.")
        return self._playlist_repo.insert(
            Playlist(id=None, name=name, description=description)
        )

    def update(self, playlist: Playlist) -> Playlist:
        """Update an existing playlist's metadata."""
        return self._playlist_repo.update(playlist)

    def delete(self, playlist_id: int) -> None:
        """Delete a playlist and clear it if it is the default."""
        self._playlist_repo.delete(playlist_id)
        if self._config_service.get_default_playlist_id() == playlist_id:
            self._config_service.set_default_playlist_id(None)

    def get(self, playlist_id: int) -> Playlist:
        """Get a playlist with its items loaded."""
        return self._playlist_repo.get_by_id(playlist_id)

    def get_all(self) -> list[Playlist]:
        """Get all playlists without loading their items."""
        return self._playlist_repo.get_all()

    def get_default_playlist_id(self) -> int | None:
        """Return the configured default playlist after validating it exists."""
        playlist_id = self._config_service.get_default_playlist_id()
        if playlist_id is None:
            return None
        try:
            self._playlist_repo.get_by_id(playlist_id)
        except PlaylistNotFoundError:
            self._config_service.set_default_playlist_id(None)
            return None
        return playlist_id

    def set_default_playlist(self, playlist_id: int | None) -> None:
        """Set or clear the default playlist preference."""
        if playlist_id is not None:
            self._playlist_repo.get_by_id(playlist_id)
        self._config_service.set_default_playlist_id(playlist_id)

    def add_songs(self, playlist_id: int, song_ids: list[int]) -> None:
        """Add original songs to the end of a playlist."""
        for song_id in song_ids:
            self._song_repo.get_by_id(song_id)
            self._playlist_repo.add_song(playlist_id, song_id)

    def add_instrumentals(self, playlist_id: int, song_ids: list[int]) -> list[int]:
        """Add available instrumental tracks and return song ids without one."""
        missing: list[int] = []
        for song_id in song_ids:
            self._song_repo.get_by_id(song_id)
            track = self._separated_track_repo.get_by_type(song_id, "instrumental")
            if track is None:
                missing.append(song_id)
                continue
            self._playlist_repo.add_instrumental(playlist_id, track.id)
        return missing

    def remove_item(self, playlist_id: int, item_id: int) -> None:
        """Remove one original-song or instrumental item from a playlist."""
        self._playlist_repo.remove_item(playlist_id, item_id)

    def reorder_items(self, playlist_id: int, item_ids: list[int]) -> None:
        """Replace the playlist order with the given item id order."""
        self._playlist_repo.reorder_items(playlist_id, item_ids)

    def get_stats(self, playlist_id: int) -> PlaylistStats:
        """Compute playlist item count and total duration."""
        items = self._playlist_repo.get_by_id(playlist_id).items
        return PlaylistStats(
            song_count=len(items),
            total_duration_ms=sum(item.duration_ms for item in items),
        )

    def get_remaining_time(
        self, playlist_id: int, reference_minutes: int = 25
    ) -> int:
        """Return remaining time in milliseconds (reference - total)."""
        return reference_minutes * 60 * 1000 - self.get_stats(
            playlist_id
        ).total_duration_ms

    def validate_export(self, playlist_id: int) -> list[str]:
        """Return warnings for playlist source files missing from disk."""
        playlist = self._playlist_repo.get_by_id(playlist_id)
        warnings = [
            f"Missing file: {item.file_path} ({item.title} by {item.artist})"
            for item in playlist.items
            if not Path(item.file_path).is_file()
        ]
        if warnings:
            logger.warning(
                "Export validation for playlist id=%d: %d warnings",
                playlist_id,
                len(warnings),
            )
        return warnings
