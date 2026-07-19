from __future__ import annotations

from dataclasses import dataclass, field

from core.enums import AudioFormat, TaskStatus, TaskType


@dataclass
class Song:
    """A song in the library, mirrors the songs table."""
    id: int | None          # None when not yet persisted
    file_path: str          # absolute path to playable audio
    title: str
    artist: str
    album: str
    duration_ms: int
    bitrate_bps: int
    sample_rate_hz: int
    channels: int           # 1 or 2
    format: str             # "mp3", "flac", "wav", "m4a"
    file_size_bytes: int
    source_file_path: str | None = None
    has_vocal_removed: bool = False
    is_normalized: bool = False
    tags: list[Tag] = field(default_factory=list)
    created_at: str = ""    # ISO 8601
    updated_at: str = ""


@dataclass
class Tag:
    """A tag for categorizing songs."""
    id: int | None
    name: str


@dataclass
class TaskInfo:
    """Represents a task in the queue, mirrors the tasks table."""
    id: int | None
    task_type: TaskType
    status: TaskStatus
    progress: float           # 0.0 ~ 1.0
    input_data: dict          # JSON-serializable input params
    output_data: dict | None = None
    error_msg: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""


@dataclass
class AudioMetadata:
    """Raw metadata extracted by FFprobe, not persisted directly."""
    file_path: str
    title: str = ""
    artist: str = ""
    album: str = ""
    duration_ms: int = 0
    bitrate_bps: int = 0
    sample_rate_hz: int = 0
    channels: int = 2
    format: str = ""
    file_size_bytes: int = 0


@dataclass
class ProcessConfig:
    """Parameters for batch audio processing / transcoding."""
    output_format: str = "mp3"
    bitrate_bps: int = 320000
    sample_rate_hz: int = 44100
    channels: int = 2
    target_loudness_lufs: float | None = None  # None = skip loudnorm


@dataclass
class ExportConfig:
    """Parameters for broadcast export."""
    output_format: str = "mp3"
    bitrate_bps: int = 320000
    sample_rate_hz: int = 44100
    reference_duration_minutes: int = 25
    crossfade_ms: int = 0
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    normalize_loudness: bool = True


@dataclass
class PlaylistStats:
    """Computed statistics for a playlist."""
    song_count: int
    total_duration_ms: int
    avg_loudness_lufs: float | None = None


@dataclass
class SeparatedTrack:
    """A separated audio track (vocals, instrumental, etc.) linked to a song."""
    id: int | None
    song_id: int
    track_type: str      # "vocals", "instrumental", "drums", "bass", "other"
    file_path: str
    created_at: str = ""


@dataclass
class PlaylistItem:
    """A playable playlist entry from a song or its separated track."""
    id: int | None
    playlist_id: int
    song: Song
    separated_track: SeparatedTrack | None = None
    sort_order: int = 0

    @property
    def file_path(self) -> str:
        """Return the audio source path for this item."""
        if self.separated_track is not None:
            return self.separated_track.file_path
        return self.song.file_path

    @property
    def title(self) -> str:
        """Return the title suitable for playlist display."""
        if self.separated_track is not None:
            return f"{self.song.title}（伴奏）"
        return self.song.title

    @property
    def artist(self) -> str:
        """Return the source song artist."""
        return self.song.artist

    @property
    def duration_ms(self) -> int:
        """Return the source song duration."""
        return self.song.duration_ms


@dataclass
class Playlist:
    """A playlist containing playable items."""
    id: int | None
    name: str
    description: str = ""
    items: list[PlaylistItem] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
