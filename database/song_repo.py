"""Song repository -- all song/tag SQL lives here."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from core.exceptions import DatabaseError, SongNotFoundError
from core.models import Song, Tag
from database.serializers import row_to_song, row_to_tag

logger = logging.getLogger(__name__)


class SongRepo:
    """Repository for Song and Tag database operations."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- CRUD ---------------------------------------------------------------

    def insert(self, song: Song) -> Song:
        """Insert a song, returning it with its new id set.

        Raises DatabaseError if the file_path already exists.
        """
        logger.debug("Inserting song: %s", song.file_path)
        now = datetime.now(timezone.utc).isoformat()
        try:
            cursor = self._conn.execute(
                "INSERT INTO songs (file_path, title, artist, album, "
                "duration_ms, bitrate_bps, sample_rate_hz, channels, format, "
                "file_size_bytes, source_file_path, has_vocal_removed, is_normalized, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    song.file_path, song.title, song.artist, song.album,
                    song.duration_ms, song.bitrate_bps, song.sample_rate_hz,
                    song.channels, song.format, song.file_size_bytes,
                    song.source_file_path, int(song.has_vocal_removed),
                    int(song.is_normalized), now, now,
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise DatabaseError(
                f"Song with file_path '{song.file_path}' already exists"
            ) from exc
        song.id = cursor.lastrowid
        song.created_at = song.updated_at = now
        return song

    def update(self, song: Song) -> Song:
        """Update song fields and updated_at.

        Raises SongNotFoundError if the song id does not exist.
        """
        if song.id is None:
            raise SongNotFoundError("Cannot update song without an id")
        logger.debug("Updating song id=%d", song.id)
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "UPDATE songs SET file_path=?, title=?, artist=?, album=?, "
            "duration_ms=?, bitrate_bps=?, sample_rate_hz=?, channels=?, "
            "format=?, file_size_bytes=?, source_file_path=?, "
            "has_vocal_removed=?, is_normalized=?, updated_at=? WHERE id=?",
            (
                song.file_path, song.title, song.artist, song.album,
                song.duration_ms, song.bitrate_bps, song.sample_rate_hz,
                song.channels, song.format, song.file_size_bytes,
                song.source_file_path, int(song.has_vocal_removed),
                int(song.is_normalized), now, song.id,
            ),
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            raise SongNotFoundError(song.id)
        song.updated_at = now
        return song

    def delete(self, song_id: int) -> None:
        """Delete a song by id.  Raises SongNotFoundError if not found."""
        logger.debug("Deleting song id=%d", song_id)
        cursor = self._conn.execute("DELETE FROM songs WHERE id=?", (song_id,))
        self._conn.commit()
        if cursor.rowcount == 0:
            raise SongNotFoundError(song_id)

    def get_by_id(self, song_id: int) -> Song:
        """Get a song by id with tags loaded.  Raises SongNotFoundError."""
        logger.debug("Getting song by id=%d", song_id)
        row = self._conn.execute(
            "SELECT * FROM songs WHERE id=?", (song_id,)
        ).fetchone()
        if row is None:
            raise SongNotFoundError(song_id)
        song = row_to_song(row)
        song.tags = self.get_tags(song_id)
        return song

    def get_by_path(self, file_path: str) -> Song | None:
        """Get a song by its file path, or None if not found."""
        logger.debug("Getting song by path: %s", file_path)
        row = self._conn.execute(
            "SELECT * FROM songs WHERE file_path=?", (file_path,)
        ).fetchone()
        if row is None:
            return None
        song = row_to_song(row)
        song.tags = self.get_tags(song.id)
        return song

    def get_by_source_path(self, source_file_path: str) -> Song | None:
        """Get a decrypted import by its original encrypted source path."""
        row = self._conn.execute(
            "SELECT * FROM songs WHERE source_file_path=?", (source_file_path,)
        ).fetchone()
        if row is None:
            return None
        song = row_to_song(row)
        song.tags = self.get_tags(song.id)
        return song

    def search(
        self, *, query: str = "", format: str = "",
        has_vocal_removed: bool | None = None,
        sort_by: str = "title", sort_desc: bool = False,
        limit: int = 100, offset: int = 0,
    ) -> list[Song]:
        """Search songs.  ``query`` matches title OR artist (LIKE %query%).

        Returns songs with their tags loaded.
        """
        logger.debug(
            "Search songs: query=%r format=%r vocal=%r "
            "sort=%s desc=%s limit=%d offset=%d",
            query, format, has_vocal_removed, sort_by, sort_desc, limit, offset,
        )
        clauses: list[str] = []
        params: list = []
        if query:
            clauses.append("(title LIKE ? OR artist LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        if format:
            clauses.append("format = ?")
            params.append(format)
        if has_vocal_removed is not None:
            clauses.append("has_vocal_removed = ?")
            params.append(int(has_vocal_removed))

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        _ALLOWED = {"title", "artist", "album", "duration_ms", "format",
                     "created_at", "updated_at", "bitrate_bps",
                     "sample_rate_hz", "file_size_bytes"}
        col = sort_by if sort_by in _ALLOWED else "title"
        order = f"ORDER BY {col} {'DESC' if sort_desc else 'ASC'}"

        sql = f"SELECT * FROM songs {where} {order} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn.execute(sql, params).fetchall()
        return [
            self._hydrate_tags(row_to_song(r), r["id"]) for r in rows
        ]

    def count(self) -> int:
        """Return the total number of songs in the database."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM songs"
        ).fetchone()[0]

    # -- Tag management -----------------------------------------------------

    def add_tag(self, song_id: int, tag_name: str) -> None:
        """Add a tag to a song (creates the tag if needed).

        Raises SongNotFoundError if song_id does not exist.
        """
        logger.debug("Adding tag '%s' to song id=%d", tag_name, song_id)
        self.get_by_id(song_id)  # verify exists
        self._conn.execute(
            "INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,)
        )
        tag_row = self._conn.execute(
            "SELECT id FROM tags WHERE name=?", (tag_name,)
        ).fetchone()
        if tag_row is None:
            raise DatabaseError(f"Failed to create or find tag '{tag_name}'")
        self._conn.execute(
            "INSERT OR IGNORE INTO song_tags (song_id, tag_id) VALUES (?, ?)",
            (song_id, tag_row["id"]),
        )
        self._conn.commit()

    def remove_tag(self, song_id: int, tag_name: str) -> None:
        """Remove a tag from a song (does not delete the tag row)."""
        logger.debug("Removing tag '%s' from song id=%d", tag_name, song_id)
        self._conn.execute(
            "DELETE FROM song_tags WHERE song_id=? AND tag_id="
            "(SELECT id FROM tags WHERE name=?)",
            (song_id, tag_name),
        )
        self._conn.commit()

    def get_tags(self, song_id: int) -> list[Tag]:
        """Return all tags for a given song, sorted by name."""
        rows = self._conn.execute(
            "SELECT t.id, t.name FROM tags t "
            "INNER JOIN song_tags st ON t.id = st.tag_id "
            "WHERE st.song_id=? ORDER BY t.name",
            (song_id,),
        ).fetchall()
        return [row_to_tag(r) for r in rows]

    def get_all_tags(self) -> list[Tag]:
        """Return every tag in the database, sorted by name."""
        rows = self._conn.execute(
            "SELECT id, name FROM tags ORDER BY name"
        ).fetchall()
        return [row_to_tag(r) for r in rows]

    # -- Helpers ------------------------------------------------------------

    def _hydrate_tags(self, song: Song, song_id: int) -> Song:
        """Attach tag list to a song and return it."""
        song.tags = self.get_tags(song_id)
        return song
