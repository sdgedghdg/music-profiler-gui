from __future__ import annotations


class MusicProfilerError(Exception):
    """Base exception for all MusicProfiler errors."""


class NcmDecryptionError(MusicProfilerError):
    """An NCM file cannot be validated or decrypted."""


class ConfigError(MusicProfilerError):
    """Configuration-related errors (missing file, invalid value, tool not found)."""


class ToolNotFoundError(ConfigError):
    """External tool (ffmpeg, demucs, um) not found at configured path."""


class ToolExecutionError(MusicProfilerError):
    """External tool returned non-zero exit code or timed out."""


class DatabaseError(MusicProfilerError):
    """Database operation failed."""


class SongNotFoundError(DatabaseError):
    """Song not found by id or path."""


class PlaylistNotFoundError(DatabaseError):
    """Playlist not found by id."""


class TaskNotFoundError(DatabaseError):
    """Task not found by id."""


class ValidationError(MusicProfilerError):
    """Input validation failed (bad format, missing field)."""


class ExportError(MusicProfilerError):
    """Export flow failed (missing songs, transcode error, merge error)."""
