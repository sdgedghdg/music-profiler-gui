"""Render a playlist as a shareable table (CSV or Markdown).

Pure helpers: no database access, no GUI, no third-party dependencies.
``PlaylistService`` uses them to write the actual file; the UI only picks a
destination path.
"""

from __future__ import annotations

import csv
import io
import re
from enum import Enum
from pathlib import Path

from core.exceptions import ValidationError
from core.formatters import format_duration
from core.i18n import t
from core.models import Playlist, PlaylistItem

__all__ = [
    "PlaylistTableFormat",
    "format_from_path",
    "render_playlist_table",
    "resolve_table_path",
    "suggest_filename",
    "write_playlist_table",
]


class PlaylistTableFormat(str, Enum):
    """Supported playlist table file formats."""

    CSV = "csv"
    MARKDOWN = "md"

    @property
    def extension(self) -> str:
        """Return the file extension including the leading dot."""
        return f".{self.value}"


_HEADERS: tuple[str, ...] = (
    "table.index",
    "table.title",
    "table.artist",
    "table.album",
    "table.variant",
    "table.duration",
    "table.cumulative",
)

_SUFFIXES: dict[str, PlaylistTableFormat] = {
    ".csv": PlaylistTableFormat.CSV,
    ".md": PlaylistTableFormat.MARKDOWN,
    ".markdown": PlaylistTableFormat.MARKDOWN,
}

_TRACK_TYPE_KEYS: dict[str, str] = {
    "instrumental": "table.variant_instrumental",
    "vocals": "table.variant_vocals",
    "drums": "table.variant_drums",
    "bass": "table.variant_bass",
    "other": "table.variant_other",
}

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Spreadsheet applications interpret cells starting with these characters as
# formulas. Prefixing an apostrophe keeps imported metadata as plain text.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def coerce_format(value: PlaylistTableFormat | str) -> PlaylistTableFormat:
    """Normalise a format enum, file extension, or format name."""
    if isinstance(value, PlaylistTableFormat):
        return value
    key = str(value).lower().lstrip(".")
    if key in ("markdown", "md"):
        return PlaylistTableFormat.MARKDOWN
    if key == "csv":
        return PlaylistTableFormat.CSV
    raise ValidationError(f"Unsupported playlist table format: {value!r}")


def format_from_path(path: str | Path) -> PlaylistTableFormat:
    """Infer the table format from a file extension.

    Raises:
        ValidationError: If the extension is not CSV / Markdown.
    """
    suffix = Path(path).suffix.lower()
    fmt = _SUFFIXES.get(suffix)
    if fmt is None:
        raise ValidationError(
            f"Unsupported playlist table format: {suffix or path}"
        )
    return fmt


def resolve_table_path(
    path: str | Path,
    fmt: PlaylistTableFormat | str | None = None,
) -> tuple[Path, PlaylistTableFormat]:
    """Return a path with a matching extension and the format to write.

    Unknown or missing extensions fall back to CSV, so a name typed by hand in
    the save dialog still produces a file that opens correctly.
    """
    target = Path(path)
    if fmt is not None:
        resolved = coerce_format(fmt)
        valid_suffixes = (
            (".md", ".markdown")
            if resolved is PlaylistTableFormat.MARKDOWN
            else (resolved.extension,)
        )
        if target.suffix.lower() not in valid_suffixes:
            if target.suffix:
                target = target.with_suffix(resolved.extension)
            else:
                target = target.with_name(target.name + resolved.extension)
        return target, resolved

    try:
        return target, format_from_path(target)
    except ValidationError:
        if target.suffix:
            target = target.with_suffix(PlaylistTableFormat.CSV.extension)
        else:
            target = target.with_name(target.name + PlaylistTableFormat.CSV.extension)
        return target, PlaylistTableFormat.CSV


def suggest_filename(
    name: str, fmt: PlaylistTableFormat | str = PlaylistTableFormat.CSV
) -> str:
    """Build a safe default file name for a playlist table."""
    resolved = coerce_format(fmt)
    safe = _UNSAFE_FILENAME_CHARS.sub("_", (name or "").strip())
    safe = safe.strip(" .")[:80] or "playlist"
    return f"{safe}{resolved.extension}"


def _text(value: object) -> str:
    """Coerce metadata that may arrive as NULL from SQLite into a string."""
    return "" if value is None else str(value)


def _variant(item: PlaylistItem) -> str:
    if item.separated_track is None:
        return t("table.variant_original")
    track_type = item.separated_track.track_type
    key = _TRACK_TYPE_KEYS.get(track_type)
    return t(key) if key else track_type


def _table_rows(playlist: Playlist) -> tuple[list[list[str]], int]:
    """Build the body rows and return them with the total duration in ms."""
    rows: list[list[str]] = []
    cumulative_ms = 0
    for index, item in enumerate(playlist.items, 1):
        cumulative_ms += item.duration_ms
        rows.append([
            str(index),
            _text(item.title),
            _text(item.artist),
            _text(item.song.album),
            _variant(item),
            format_duration(item.duration_ms),
            format_duration(cumulative_ms),
        ])
    # A summary row keeps printed lists usable without a spreadsheet formula.
    rows.append([
        t("table.total"),
        t("table.song_count").format(count=len(playlist.items)),
        "", "", "",
        format_duration(cumulative_ms),
        "",
    ])
    return rows, cumulative_ms


def _csv_cell(value: str) -> str:
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


def _md_cell(value: object) -> str:
    """Escape a value for a Markdown table cell."""
    return (
        _text(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
    )


def render_csv(playlist: Playlist) -> str:
    """Render the playlist as RFC 4180 CSV text (CRLF line endings)."""
    rows, _ = _table_rows(playlist)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([t(key) for key in _HEADERS])
    for row in rows:
        writer.writerow([_csv_cell(cell) for cell in row])
    return buffer.getvalue()


def render_markdown(playlist: Playlist) -> str:
    """Render the playlist as a Markdown document with a table."""
    rows, total_ms = _table_rows(playlist)
    description = _text(playlist.description)
    lines = [
        f"# {t('table.doc_title').format(name=_md_cell(playlist.name))}",
        "",
        f"- {t('table.song_count').format(count=len(playlist.items))}",
        f"- {t('table.total_duration').format(duration=format_duration(total_ms))}",
    ]
    if description.strip():
        lines.append(
            f"- {t('table.description').format(description=_md_cell(description))}"
        )
    lines.append("")
    lines.append("| " + " | ".join(_md_cell(t(key)) for key in _HEADERS) + " |")
    lines.append("| " + " | ".join("---" for _ in _HEADERS) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(cell) for cell in row) + " |")
    lines.append("")
    return "\n".join(lines)


def render_playlist_table(
    playlist: Playlist, fmt: PlaylistTableFormat | str
) -> str:
    """Render *playlist* in the requested format."""
    resolved = coerce_format(fmt)
    if resolved is PlaylistTableFormat.CSV:
        return render_csv(playlist)
    return render_markdown(playlist)


def write_playlist_table(
    playlist: Playlist,
    destination: str | Path,
    fmt: PlaylistTableFormat | str | None = None,
) -> Path:
    """Write the rendered table to *destination* and return the final path.

    CSV uses UTF-8 with BOM so Excel opens Chinese text correctly. Parent
    directories are created when missing.
    """
    path, resolved = resolve_table_path(destination, fmt)
    content = render_playlist_table(playlist, resolved)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if resolved is PlaylistTableFormat.CSV else "utf-8"
    path.write_text(content, encoding=encoding, newline="")
    return path
