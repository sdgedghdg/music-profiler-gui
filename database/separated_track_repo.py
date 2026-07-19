"""Repository for separated track persistence."""

from __future__ import annotations

import sqlite3

from core.models import SeparatedTrack
from database.serializers import row_to_separated_track


class SeparatedTrackRepo:
    """CRUD operations for the separated_tracks table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------ #
    #  Create
    # ------------------------------------------------------------------ #

    def insert(self, track: SeparatedTrack) -> SeparatedTrack:
        """Insert a new separated track and return it with the generated id."""
        cursor = self._conn.execute(
            "INSERT INTO separated_tracks (song_id, track_type, file_path) "
            "VALUES (?, ?, ?)",
            (track.song_id, track.track_type, track.file_path),
        )
        self._conn.commit()
        track.id = cursor.lastrowid
        return track

    # ------------------------------------------------------------------ #
    #  Read
    # ------------------------------------------------------------------ #

    def get_by_id(self, track_id: int) -> SeparatedTrack | None:
        """Return a separated track by id, or None if it does not exist."""
        row = self._conn.execute(
            "SELECT * FROM separated_tracks WHERE id = ?", (track_id,)
        ).fetchone()
        if row is None:
            return None
        return row_to_separated_track(row)

    def get_by_song(self, song_id: int) -> list[SeparatedTrack]:
        """Return all separated tracks for a given song."""
        rows = self._conn.execute(
            "SELECT * FROM separated_tracks WHERE song_id = ? ORDER BY id",
            (song_id,),
        ).fetchall()
        return [row_to_separated_track(r) for r in rows]

    def get_by_type(self, song_id: int, track_type: str) -> SeparatedTrack | None:
        """Return the separated track of a given type for a song, or None."""
        row = self._conn.execute(
            "SELECT * FROM separated_tracks "
            "WHERE song_id = ? AND track_type = ?",
            (song_id, track_type),
        ).fetchone()
        if row is None:
            return None
        return row_to_separated_track(row)

    # ------------------------------------------------------------------ #
    #  Delete
    # ------------------------------------------------------------------ #

    def delete_by_song(self, song_id: int) -> None:
        """Delete all separated tracks belonging to a song."""
        self._conn.execute(
            "DELETE FROM separated_tracks WHERE song_id = ?", (song_id,),
        )
        self._conn.commit()

    def delete(self, track_id: int) -> None:
        """Delete a single separated track by its id."""
        self._conn.execute(
            "DELETE FROM separated_tracks WHERE id = ?", (track_id,),
        )
        self._conn.commit()
