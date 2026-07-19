"""Shared row-to-model serializers for database repositories."""

from __future__ import annotations

import sqlite3

from core.models import PlaylistItem, SeparatedTrack, Song, Tag


def row_to_song(row: sqlite3.Row) -> Song:
    """Convert a sqlite3.Row to a Song dataclass."""
    return Song(
        id=row["id"],
        file_path=row["file_path"],
        title=row["title"],
        artist=row["artist"],
        album=row["album"],
        duration_ms=row["duration_ms"],
        bitrate_bps=row["bitrate_bps"],
        sample_rate_hz=row["sample_rate_hz"],
        channels=row["channels"],
        format=row["format"],
        file_size_bytes=row["file_size_bytes"],
        source_file_path=row["source_file_path"],
        has_vocal_removed=bool(row["has_vocal_removed"]),
        is_normalized=bool(row["is_normalized"]),
        tags=[],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_tag(row: sqlite3.Row) -> Tag:
    """Convert a sqlite3.Row to a Tag dataclass."""
    return Tag(id=row["id"], name=row["name"])


def row_to_separated_track(row: sqlite3.Row) -> SeparatedTrack:
    """Convert a sqlite3.Row to a SeparatedTrack dataclass."""
    return SeparatedTrack(
        id=row["id"],
        song_id=row["song_id"],
        track_type=row["track_type"],
        file_path=row["file_path"],
        created_at=row["created_at"],
    )


def row_to_playlist_item(row: sqlite3.Row) -> PlaylistItem:
    """Convert a playlist item join row to a PlaylistItem dataclass."""
    song = row_to_song(row)
    track = None
    if row["separated_track_id"] is not None:
        track = SeparatedTrack(
            id=row["separated_track_id"],
            song_id=row["separated_track_song_id"],
            track_type=row["separated_track_type"],
            file_path=row["separated_track_file_path"],
            created_at=row["separated_track_created_at"],
        )
    return PlaylistItem(
        id=row["playlist_item_id"],
        playlist_id=row["playlist_id"],
        song=song,
        separated_track=track,
        sort_order=row["sort_order"],
    )
