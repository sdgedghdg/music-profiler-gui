"""Schema migrations."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

LATEST_VERSION = 6


def run_migrations(conn: sqlite3.Connection) -> None:
    """Run database migrations to bring schema to the latest version.

    Args:
        conn: An open sqlite3.Connection.
    """
    _ensure_schema_version_table(conn)
    current = _get_version(conn)
    logger.info("Current schema version: %d, latest: %d", current, LATEST_VERSION)

    if current < 1:
        _migration_001(conn)
        _set_version(conn, 1)
        logger.info("Applied migration 001: initial schema")

    if current < 2:
        _migration_002(conn)
        _set_version(conn, 2)
        logger.info("Applied migration 002: missing indexes")

    if current < 3:
        _migration_003(conn)
        _set_version(conn, 3)
        logger.info("Applied migration 003: separated tracks")

    if current < 4:
        _migration_004(conn)
        _set_version(conn, 4)
        logger.info("Applied migration 004: playlist items")

    if current < 5:
        _migration_005(conn)
        _set_version(conn, 5)
        logger.info("Applied migration 005: encrypted music sources")

    if current < 6:
        _migration_006(conn)
        _set_version(conn, 6)
        logger.info("Applied migration 006: native NCM imports")


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    """Create schema_version table if it doesn't exist, seed version 0 if empty."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "    version INTEGER NOT NULL"
        ")"
    )
    existing = conn.execute(
        "SELECT COUNT(*) AS cnt FROM schema_version"
    ).fetchone()
    if existing["cnt"] == 0:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
        conn.commit()


def _get_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    ).fetchone()
    return row["version"]


def _set_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute("UPDATE schema_version SET version = ?", (version,))
    conn.commit()


def _migration_001(conn: sqlite3.Connection) -> None:
    """Create initial tables and indexes (version 1)."""
    # ---- Songs ----
    conn.execute(
        "CREATE TABLE IF NOT EXISTS songs ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    file_path TEXT NOT NULL UNIQUE,"
        "    title TEXT NOT NULL DEFAULT '',"
        "    artist TEXT NOT NULL DEFAULT '',"
        "    album TEXT NOT NULL DEFAULT '',"
        "    duration_ms INTEGER NOT NULL DEFAULT 0,"
        "    bitrate_bps INTEGER NOT NULL DEFAULT 0,"
        "    sample_rate_hz INTEGER NOT NULL DEFAULT 0,"
        "    channels INTEGER NOT NULL DEFAULT 2,"
        "    format TEXT NOT NULL DEFAULT '',"
        "    file_size_bytes INTEGER NOT NULL DEFAULT 0,"
        "    has_vocal_removed INTEGER NOT NULL DEFAULT 0,"
        "    is_normalized INTEGER NOT NULL DEFAULT 0,"
        "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )

    # ---- Tags ----
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tags ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    name TEXT NOT NULL UNIQUE"
        ")"
    )

    # ---- Song-tag junction ----
    conn.execute(
        "CREATE TABLE IF NOT EXISTS song_tags ("
        "    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,"
        "    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,"
        "    PRIMARY KEY (song_id, tag_id)"
        ")"
    )

    # ---- Playlists ----
    conn.execute(
        "CREATE TABLE IF NOT EXISTS playlists ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    name TEXT NOT NULL,"
        "    description TEXT NOT NULL DEFAULT '',"
        "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "    updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )

    # ---- Playlist-song junction ----
    conn.execute(
        "CREATE TABLE IF NOT EXISTS playlist_songs ("
        "    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,"
        "    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,"
        "    sort_order INTEGER NOT NULL DEFAULT 0,"
        "    PRIMARY KEY (playlist_id, song_id)"
        ")"
    )

    # ---- Tasks ----
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tasks ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    task_type TEXT NOT NULL,"
        "    status TEXT NOT NULL DEFAULT 'pending',"
        "    progress REAL NOT NULL DEFAULT 0.0,"
        "    input_data TEXT NOT NULL DEFAULT '{}',"
        "    output_data TEXT,"
        "    error_msg TEXT NOT NULL DEFAULT '',"
        "    created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "    started_at TEXT,"
        "    finished_at TEXT"
        ")"
    )

    # ---- Indexes ----
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_songs_file_path ON songs(file_path)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_songs_title ON songs(title)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_songs_artist ON songs(artist)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_songs_format ON songs(format)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_playlist_songs_lookup "
        "ON playlist_songs(playlist_id, sort_order)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_song_tags_song_id ON song_tags(song_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)"
    )

    conn.commit()


def _migration_002(conn: sqlite3.Connection) -> None:
    """Add missing indexes (version 2)."""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_playlist_songs_lookup "
        "ON playlist_songs(playlist_id, sort_order)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_song_tags_song_id ON song_tags(song_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)"
    )
    conn.commit()


def _migration_003(conn: sqlite3.Connection) -> None:
    """Add separated_tracks table (version 3)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS separated_tracks ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,"
        "    track_type TEXT NOT NULL,"
        "    file_path TEXT NOT NULL,"
        "    created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    conn.commit()


def _migration_004(conn: sqlite3.Connection) -> None:
    """Replace playlist-song links with entries supporting instrumentals."""
    conn.execute(
        "CREATE TABLE playlist_items ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,"
        "    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,"
        "    separated_track_id INTEGER REFERENCES separated_tracks(id) ON DELETE CASCADE,"
        "    sort_order INTEGER NOT NULL DEFAULT 0"
        ")"
    )
    conn.execute(
        "INSERT INTO playlist_items "
        "(playlist_id, song_id, separated_track_id, sort_order) "
        "SELECT playlist_id, song_id, NULL, sort_order FROM playlist_songs"
    )
    conn.execute("DROP TABLE playlist_songs")
    conn.execute(
        "CREATE INDEX idx_playlist_items_lookup "
        "ON playlist_items(playlist_id, sort_order)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX idx_playlist_items_original "
        "ON playlist_items(playlist_id, song_id) "
        "WHERE separated_track_id IS NULL"
    )
    conn.commit()


def _migration_005(conn: sqlite3.Connection) -> None:
    """Track encrypted source paths for persisted decrypted audio."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(songs)")}
    if "source_file_path" not in columns:
        conn.execute("ALTER TABLE songs ADD COLUMN source_file_path TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_songs_source_file_path "
        "ON songs(source_file_path)"
    )
    conn.commit()


def _migration_006(conn: sqlite3.Connection) -> None:
    """Reserve a schema version for native NCM import semantics."""
    _migration_005(conn)
