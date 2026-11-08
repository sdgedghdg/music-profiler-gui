"""SQLite connection management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

#: How long a writer waits for a competing lock before raising ``database is
#: locked``.  The UI thread and the worker thread hold separate connections, so
#: without this a brief write-write overlap surfaces as an error in the GUI.
_BUSY_TIMEOUT_MS = 5000


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open (or create) SQLite database, enable WAL, foreign keys, and row factory.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A configured sqlite3.Connection with WAL mode, foreign keys enabled,
        a busy timeout, and sqlite3.Row as row factory.
    """
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    conn.row_factory = sqlite3.Row
    return conn
