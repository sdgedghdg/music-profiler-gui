from __future__ import annotations

from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AudioFormat(Enum):
    MP3 = "mp3"
    FLAC = "flac"
    WAV = "wav"
    M4A = "m4a"


class TaskType(Enum):
    IMPORT = "import"
    TRANSCODE = "transcode"
    DEMUCS = "demucs"
    EXPORT = "export"
    DECRYPT = "decrypt"
