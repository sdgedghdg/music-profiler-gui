"""Playlist repository."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from core.exceptions import PlaylistNotFoundError, ValidationError
from core.models import Playlist, PlaylistItem
from database.serializers import row_to_playlist_item

logger = logging.getLogger(__name__)


def _row_to_playlist(row: sqlite3.Row) -> Playlist:
    """Convert a sqlite3.Row to a Playlist dataclass."""
    return Playlist(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PlaylistRepo:
    """Repository for playlist database operations."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialise with a shared SQLite connection."""
        self._conn = conn

    def insert(self, playlist: Playlist) -> Playlist:
        """Insert a new playlist and return it with id set."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "INSERT INTO playlists (name, description, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (playlist.name, playlist.description, now, now),
        )
        self._conn.commit()
        playlist.id = cursor.lastrowid
        playlist.created_at = now
        playlist.updated_at = now
        return playlist

    def update(self, playlist: Playlist) -> Playlist:
        """Update playlist metadata."""
        if playlist.id is None:
            raise PlaylistNotFoundError("Cannot update playlist without an id")
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "UPDATE playlists SET name=?, description=?, updated_at=? "
            "WHERE id=?",
            (playlist.name, playlist.description, now, playlist.id),
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            raise PlaylistNotFoundError(playlist.id)
        playlist.updated_at = now
        return playlist

    def delete(self, playlist_id: int) -> None:
        """Delete a playlist and all of its items."""
        cursor = self._conn.execute(
            "DELETE FROM playlists WHERE id=?", (playlist_id,)
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            raise PlaylistNotFoundError(playlist_id)

    def get_by_id(self, playlist_id: int) -> Playlist:
        """Get a playlist with items loaded in sort order."""
        row = self._conn.execute(
            "SELECT * FROM playlists WHERE id=?", (playlist_id,)
        ).fetchone()
        if row is None:
            raise PlaylistNotFoundError(playlist_id)
        playlist = _row_to_playlist(row)
        playlist.items = self._load_items(playlist_id)
        return playlist

    def get_all(self) -> list[Playlist]:
        """Return all playlists, ordered by name, without items."""
        rows = self._conn.execute(
            "SELECT * FROM playlists ORDER BY name"
        ).fetchall()
        return [_row_to_playlist(row) for row in rows]

    def add_song(self, playlist_id: int, song_id: int) -> None:
        """Append an original song item to a playlist."""
        self._add_item(playlist_id, song_id, None)

    def add_instrumental(self, playlist_id: int, track_id: int) -> None:
        """Append an instrumental separated track to a playlist."""
        row = self._conn.execute(
            "SELECT song_id FROM separated_tracks WHERE id=?", (track_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Separated track id={track_id} does not exist")
        self._add_item(playlist_id, row["song_id"], track_id)

    def remove_item(self, playlist_id: int, item_id: int) -> None:
        """Remove one item from a playlist."""
        self._conn.execute(
            "DELETE FROM playlist_items WHERE playlist_id=? AND id=?",
            (playlist_id, item_id),
        )
        self._conn.commit()

    def reorder_items(self, playlist_id: int, item_ids: list[int]) -> None:
        """Replace item order after ensuring it contains every item exactly once."""
        self.get_by_id(playlist_id)
        rows = self._conn.execute(
            "SELECT id FROM playlist_items WHERE playlist_id=?", (playlist_id,)
        ).fetchall()
        current_ids = {row["id"] for row in rows}
        if len(item_ids) != len(current_ids) or set(item_ids) != current_ids:
            raise ValueError("Item order must contain every playlist item exactly once")
        for index, item_id in enumerate(item_ids):
            self._conn.execute(
                "UPDATE playlist_items SET sort_order=? WHERE id=?", (index, item_id)
            )
        self._conn.commit()

    def _add_item(
        self, playlist_id: int, song_id: int, separated_track_id: int | None
    ) -> None:
        self.get_by_id(playlist_id)
        # The UNIQUE index only covers original songs (separated_track_id IS
        # NULL), so instrumentals need an explicit duplicate check to keep the
        # two cases consistent.
        if separated_track_id is not None:
            duplicate = self._conn.execute(
                "SELECT 1 FROM playlist_items "
                "WHERE playlist_id=? AND song_id=? AND separated_track_id=?",
                (playlist_id, song_id, separated_track_id),
            ).fetchone()
            if duplicate is not None:
                raise ValidationError("这首歌已经在歌单中了")
        row = self._conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) AS max_order "
            "FROM playlist_items WHERE playlist_id=?",
            (playlist_id,),
        ).fetchone()
        try:
            self._conn.execute(
                "INSERT INTO playlist_items "
                "(playlist_id, song_id, separated_track_id, sort_order) "
                "VALUES (?, ?, ?, ?)",
                (playlist_id, song_id, separated_track_id, row["max_order"] + 1),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            self._conn.rollback()
            raise ValidationError("这首歌已经在歌单中了") from exc

    def _load_items(self, playlist_id: int) -> list[PlaylistItem]:
        rows = self._conn.execute(
            "SELECT pi.id AS playlist_item_id, pi.playlist_id, pi.sort_order, "
            "s.*, st.id AS separated_track_id, "
            "st.song_id AS separated_track_song_id, "
            "st.track_type AS separated_track_type, "
            "st.file_path AS separated_track_file_path, "
            "st.created_at AS separated_track_created_at "
            "FROM playlist_items pi JOIN songs s ON s.id = pi.song_id "
            "LEFT JOIN separated_tracks st ON st.id = pi.separated_track_id "
            "WHERE pi.playlist_id=? ORDER BY pi.sort_order, pi.id",
            (playlist_id,),
        ).fetchall()
        return [row_to_playlist_item(row) for row in rows]
