"""Tests for exporting a playlist as a CSV / Markdown table."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from core.exceptions import PlaylistNotFoundError, ValidationError
from core.i18n import Lang, get_lang, set_lang
from core.models import Playlist, PlaylistItem, SeparatedTrack, Song
from core.playlist_table import (
    PlaylistTableFormat,
    coerce_format,
    format_from_path,
    render_playlist_table,
    resolve_table_path,
    suggest_filename,
    write_playlist_table,
)


def _song(
    title: str = "Song",
    *,
    artist: str = "Artist",
    album: str = "Album",
    duration_ms: int = 180_000,
    song_id: int | None = None,
) -> Song:
    return Song(
        id=song_id,
        file_path="track.mp3",
        title=title,
        artist=artist,
        album=album,
        duration_ms=duration_ms,
        bitrate_bps=320_000,
        sample_rate_hz=44_100,
        channels=2,
        format="mp3",
        file_size_bytes=1024,
    )


def _item(
    song: Song, item_id: int, track_type: str | None = None
) -> PlaylistItem:
    track = (
        SeparatedTrack(
            id=100 + item_id,
            song_id=song.id,
            track_type=track_type,
            file_path="separated.mp3",
        )
        if track_type
        else None
    )
    return PlaylistItem(
        id=item_id, playlist_id=1, song=song, separated_track=track
    )


def _playlist(
    items: list[PlaylistItem] | None = None,
    *,
    name: str = "Morning",
    description: str = "",
) -> Playlist:
    return Playlist(
        id=1,
        name=name,
        description=description,
        items=[_item(_song(), 1)] if items is None else items,
    )


def _csv_rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline="")))


@pytest.fixture
def playlist_service(playlist_repo, song_repo, separated_track_repo, tmp_path):
    from services.config_service import ConfigService
    from services.playlist_service import PlaylistService

    return PlaylistService(
        playlist_repo,
        song_repo,
        separated_track_repo,
        ConfigService(tmp_path / "config"),
    )


# -- Rendering -----------------------------------------------------------


def test_csv_contains_headers_rows_and_total():
    text = render_playlist_table(_playlist(), PlaylistTableFormat.CSV)

    rows = _csv_rows(text)
    assert rows[0] == ["序号", "曲名", "歌手", "专辑", "版本", "时长", "累计时长"]
    assert rows[1] == ["1", "Song", "Artist", "Album", "原曲", "3:00", "3:00"]
    assert rows[2] == ["合计", "1 首", "", "", "", "3:00", ""]
    assert text.endswith("\r\n")


def test_csv_file_uses_utf8_bom_without_double_crlf(tmp_path):
    path = write_playlist_table(_playlist(), tmp_path / "list.csv")
    raw = path.read_bytes()

    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw
    assert b"\r\r\n" not in raw
    assert "曲名".encode("utf-8") in raw


def test_csv_escapes_commas_quotes_newlines_and_formulas():
    tricky = 'A, "B"\nNext line'
    playlist = _playlist([
        _item(_song(tricky), 1),
        _item(_song("=1+1"), 2),
        _item(_song("@SUM(A1:A2)"), 3),
    ])

    rows = _csv_rows(render_playlist_table(playlist, "csv"))

    assert rows[1][1] == tricky
    assert rows[2][1] == "'=1+1"       # spreadsheet formula injection guard
    assert rows[3][1] == "'@SUM(A1:A2)"


def test_markdown_escapes_pipes_backslashes_and_newlines():
    playlist = _playlist(
        [_item(_song("A|B\\C\nD"), 1)],
        name="Morning | Show\nNext",
        description="Line one\nLine two",
    )

    text = render_playlist_table(playlist, PlaylistTableFormat.MARKDOWN)
    lines = text.splitlines()

    assert lines[0].startswith("# 歌单 — ")
    assert "<br>" in lines[0]
    assert "\\|" in lines[0]
    assert "说明：Line one<br>Line two" in text
    table_rows = [line for line in lines if line.startswith("|")]
    assert len(table_rows) == 4  # header, separator, song, total
    assert all(row.endswith(" |") for row in table_rows)
    assert len(table_rows[3].split("|")) == 9  # 7 columns + outer pipes
    assert "A\\|B\\\\C<br>D" in table_rows[2]
    assert "总时长：3:00" in text


def test_variants_and_cumulative_duration():
    song = _song("Title", duration_ms=180_000)
    playlist = _playlist([
        _item(song, 1),
        _item(_song("Title", duration_ms=150_000), 2, "instrumental"),
        _item(_song("Title", duration_ms=60_000), 3, "vocals"),
        _item(_song("Title", duration_ms=30_000), 4, "custom"),
    ])

    rows = _csv_rows(render_playlist_table(playlist, "csv"))

    assert [row[4] for row in rows[1:5]] == ["原曲", "伴奏", "人声", "custom"]
    assert [row[6] for row in rows[1:5]] == ["3:00", "5:30", "6:30", "7:00"]
    assert rows[2][1] == "Title（伴奏）"
    assert rows[5] == ["合计", "4 首", "", "", "", "7:00", ""]


def test_empty_playlist_still_produces_a_usable_table():
    playlist = _playlist([], name="Empty")

    rows = _csv_rows(render_playlist_table(playlist, "csv"))

    assert len(rows) == 2  # header + total
    assert rows[1] == ["合计", "0 首", "", "", "", "0:00", ""]
    assert "总时长：0:00" in render_playlist_table(playlist, "md")


def test_headers_follow_active_language():
    previous = get_lang()
    try:
        set_lang(Lang.EN)
        rows = _csv_rows(render_playlist_table(_playlist(), "csv"))
        assert rows[0] == [
            "#", "Title", "Artist", "Album", "Version", "Duration", "Cumulative"
        ]
        assert rows[1][4] == "Original"
        assert rows[2][0] == "Total"
    finally:
        set_lang(previous)


# -- Path / format helpers -----------------------------------------------


def test_format_from_path_and_coerce_format():
    assert format_from_path("list.CSV") is PlaylistTableFormat.CSV
    assert format_from_path("list.md") is PlaylistTableFormat.MARKDOWN
    assert format_from_path("list.markdown") is PlaylistTableFormat.MARKDOWN
    assert coerce_format("CSV") is PlaylistTableFormat.CSV
    assert coerce_format(".Markdown") is PlaylistTableFormat.MARKDOWN
    assert coerce_format(PlaylistTableFormat.MARKDOWN) is PlaylistTableFormat.MARKDOWN

    with pytest.raises(ValidationError):
        format_from_path("list.txt")
    with pytest.raises(ValidationError):
        coerce_format("xlsx")


def test_resolve_table_path_adds_or_replaces_extension(tmp_path):
    assert resolve_table_path("list") == (
        Path("list.csv"), PlaylistTableFormat.CSV
    )
    assert resolve_table_path("list.txt") == (
        Path("list.csv"), PlaylistTableFormat.CSV
    )
    assert resolve_table_path("list.MD") == (
        Path("list.MD"), PlaylistTableFormat.MARKDOWN
    )
    assert resolve_table_path("list.md", "csv") == (
        Path("list.csv"), PlaylistTableFormat.CSV
    )
    assert resolve_table_path("list", "markdown") == (
        Path("list.md"), PlaylistTableFormat.MARKDOWN
    )


def test_suggest_filename_removes_illegal_characters():
    assert suggest_filename('  A/B:C*?"<>|  ') == "A_B_C______.csv"
    assert suggest_filename("...") == "playlist.csv"
    assert suggest_filename("") == "playlist.csv"
    assert suggest_filename("Morning", "markdown") == "Morning.md"
    assert len(suggest_filename("x" * 200)) <= 84


# -- Service integration -------------------------------------------------


def test_service_writes_csv_and_markdown_and_creates_parent(
    tmp_path, playlist_service, playlist_repo, song_repo
):
    song = song_repo.insert(_song("On Air"))
    playlist = playlist_repo.insert(Playlist(id=None, name="晨间广播"))
    playlist_service.add_songs(playlist.id, [song.id])

    nested = tmp_path / "nested" / "folder" / "list.csv"
    written = playlist_service.export_table(playlist.id, nested)

    assert written == nested
    assert written.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "On Air" in written.read_text(encoding="utf-8-sig")

    md_path = playlist_service.export_table(playlist.id, tmp_path / "list.md")
    assert "# 歌单 — 晨间广播" in md_path.read_text(encoding="utf-8")

    forced = playlist_service.export_table(
        playlist.id, tmp_path / "typed.txt", PlaylistTableFormat.CSV
    )
    assert forced.name == "typed.csv"
    assert forced.exists()


def test_service_rejects_unknown_playlist(tmp_path, playlist_service):
    with pytest.raises(PlaylistNotFoundError):
        playlist_service.export_table(9999, tmp_path / "list.csv")


# -- UI callback (no Tk root needed) -------------------------------------


def test_ui_export_callback_passes_path_and_format(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import ui.playlist_panel as panel_module

    service = MagicMock()
    service.get.return_value = Playlist(id=3, name="Morning", items=[])
    service.export_table.return_value = Path("out/list.md")
    panel = SimpleNamespace(_playlist_id=3, _playlist_service=service)
    ask = MagicMock(return_value="out/list.md")
    showinfo = MagicMock()
    monkeypatch.setattr(panel_module.filedialog, "asksaveasfilename", ask)
    monkeypatch.setattr(panel_module.messagebox, "showinfo", showinfo)

    panel_module.PlaylistPanel._on_export_table(panel)

    ask.assert_called_once()
    assert ask.call_args.kwargs["initialfile"] == "Morning.csv"
    assert [types[1] for types in ask.call_args.kwargs["filetypes"]] == [
        "*.csv", "*.md"
    ]
    path_arg, fmt_arg = service.export_table.call_args.args[1:]
    assert path_arg == Path("out/list.md")
    assert fmt_arg is PlaylistTableFormat.MARKDOWN
    showinfo.assert_called_once()


def test_ui_export_callback_without_selection(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import ui.playlist_panel as panel_module

    panel = SimpleNamespace(_playlist_id=None, _playlist_service=MagicMock())
    warn, ask = MagicMock(), MagicMock()
    monkeypatch.setattr(panel_module.messagebox, "showwarning", warn)
    monkeypatch.setattr(panel_module.filedialog, "asksaveasfilename", ask)

    panel_module.PlaylistPanel._on_export_table(panel)

    warn.assert_called_once()
    ask.assert_not_called()


def test_ui_export_callback_reports_failure(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import ui.playlist_panel as panel_module

    service = MagicMock()
    service.get.return_value = Playlist(id=3, name="Morning", items=[])
    service.export_table.side_effect = OSError("disk full")
    panel = SimpleNamespace(_playlist_id=3, _playlist_service=service)
    showerror, showinfo = MagicMock(), MagicMock()
    monkeypatch.setattr(
        panel_module.filedialog, "asksaveasfilename",
        MagicMock(return_value="out/list.csv"),
    )
    monkeypatch.setattr(panel_module.messagebox, "showerror", showerror)
    monkeypatch.setattr(panel_module.messagebox, "showinfo", showinfo)

    panel_module.PlaylistPanel._on_export_table(panel)

    showerror.assert_called_once()
    assert "disk full" in showerror.call_args.args[1]
    showinfo.assert_not_called()
