"""Library panel — manage the audio library."""

from __future__ import annotations

import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import tkinter.simpledialog as simpledialog
from tkinter import Event, Menu
from typing import TYPE_CHECKING

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from core.formatters import format_duration
from core.i18n import t

if TYPE_CHECKING:
    from core.models import Song
    from services.library_service import LibraryService
    from services.playlist_service import PlaylistService
    from services.task_service import TaskService

_FORMATS: list[str] = [t("library.all"), "mp3", "flac", "wav", "m4a"]


class LibraryPanel(ttk.Frame):
    """Library management interface.

    Toolbar with import / search / format-filter / refresh, a multi-column
    Treeview for browsing songs, and a status bar with result counts.
    """

    def __init__(
        self,
        parent: ttk.Frame,
        library_service: LibraryService,
        task_service: TaskService,
        playlist_service: PlaylistService | None = None,
        on_playlist_changed=None,
    ) -> None:
        super().__init__(parent)
        self._library_service = library_service
        self._task_service = task_service
        self._playlist_service = playlist_service
        self._on_playlist_changed = on_playlist_changed
        self._songs: list[Song] = []
        self._total_count: int = 0
        self._context_menu: Menu | None = None
        self._build_ui()
        self._refresh_song_list()

    # -------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Create and lay out all widgets."""
        # -- Toolbar -----------------------------------------------------
        toolbar = ttk.Frame(self, padding=(5, 5))
        toolbar.pack(fill=X)

        ttk.Button(toolbar, text=t("library.import"), bootstyle="primary",
                   command=self._on_import).pack(side=LEFT, padx=(0, 5))

        ttk.Button(toolbar, text=t("library.import_separated"),
                   bootstyle="primary",
                   command=self._on_import_separated).pack(
            side=LEFT, padx=(0, 10))

        self._search_var = ttk.StringVar()
        entry = ttk.Entry(toolbar, textvariable=self._search_var, width=22)
        entry.pack(side=LEFT, padx=(0, 5))
        entry.bind("<Return>", lambda _e: self._on_search())

        ttk.Button(toolbar, text=t("library.search"), bootstyle="info",
                   command=self._on_search).pack(side=LEFT, padx=(0, 10))

        ttk.Label(toolbar, text=t("library.format")).pack(side=LEFT, padx=(0, 2))
        self._format_var = ttk.StringVar(value=_FORMATS[0])
        fmt_cb = ttk.Combobox(toolbar, textvariable=self._format_var,
                              values=_FORMATS, state="readonly", width=6)
        fmt_cb.pack(side=LEFT, padx=(0, 5))
        fmt_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_search())

        ttk.Button(toolbar, text=t("library.refresh"), bootstyle="secondary",
                   command=self._refresh_song_list).pack(side=LEFT)

        # -- Treeview ----------------------------------------------------
        cols = ("title", "artist", "album", "duration",
                "format", "vocal_removed", "tags")
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                  selectmode="browse")
        self._tree.heading("title", text=t("library.title"))
        self._tree.heading("artist", text=t("library.artist"))
        self._tree.heading("album", text=t("library.album"))
        self._tree.heading("duration", text=t("library.duration"))
        self._tree.heading("format", text=t("library.format_col"))
        self._tree.heading("vocal_removed", text=t("library.vocal_removed"))
        self._tree.heading("tags", text=t("library.tags"))

        widths = {"title": 200, "artist": 150, "album": 150, "duration": 70,
                  "format": 60, "vocal_removed": 100, "tags": 150}
        anchors = {"duration": CENTER, "format": CENTER,
                   "vocal_removed": CENTER}
        for col in cols:
            self._tree.column(col, width=widths[col], minwidth=40,
                              anchor=anchors.get(col, W))

        scrollbar = ttk.Scrollbar(self, orient=VERTICAL,
                                  command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Button-3>", self._on_right_click)

        # -- Status bar --------------------------------------------------
        self._status_var = ttk.StringVar(value=t("library.ready"))
        status_frame = ttk.Frame(self)
        status_frame.pack(fill=X, padx=1, pady=1)
        ttk.Label(status_frame, textvariable=self._status_var, relief=SUNKEN).pack(
            side=LEFT, fill=X, expand=True
        )
        self._default_playlist_var = ttk.StringVar()
        ttk.Label(status_frame, textvariable=self._default_playlist_var).pack(
            side=RIGHT, padx=5
        )
        self.refresh_default_playlist_summary()

    # -------------------------------------------------------------------
    def _refresh_song_list(self) -> None:
        """Reload songs from the service and repopulate the treeview."""
        self._total_count = self._library_service.count()

        query = self._search_var.get().strip()
        fmt_val = self._format_var.get()
        format_filter = "" if fmt_val == _FORMATS[0] else fmt_val

        self._songs = self._library_service.search(
            query=query, format=format_filter, limit=100_000)

        # One batched query instead of one round-trip per row.
        track_counts = self._library_service.get_separated_tracks_counts(
            [song.id for song in self._songs])

        self._tree.delete(*self._tree.get_children())
        for song in self._songs:
            vocal_col = ""
            if song.has_vocal_removed:
                count = track_counts.get(song.id, 0)
                vocal_col = f"✓ ({count} tracks)"
            self._tree.insert("", END, iid=str(song.id), values=(
                song.title, song.artist, song.album,
                format_duration(song.duration_ms), song.format,
                vocal_col,
                ", ".join(t.name for t in song.tags),
            ))

        if query or format_filter:
            self._status_var.set(
                t("library.showing_filtered").format(
                    shown=len(self._songs), total=self._total_count))
        else:
            self._status_var.set(
                t("library.showing").format(
                    shown=len(self._songs), total=self._total_count))

    def refresh_default_playlist_summary(self) -> None:
        """Update the selected default playlist's duration summary."""
        if self._playlist_service is None:
            self._default_playlist_var.set("")
            return
        playlist_id = self._playlist_service.get_default_playlist_id()
        if playlist_id is None:
            self._default_playlist_var.set(t("library.no_default_playlist"))
            return
        try:
            playlist = self._playlist_service.get(playlist_id)
            stats = self._playlist_service.get_stats(playlist_id)
        except Exception:
            self._playlist_service.set_default_playlist(None)
            self._default_playlist_var.set(t("library.no_default_playlist"))
            return
        self._default_playlist_var.set(
            t("library.default_playlist").format(
                name=playlist.name,
                duration=format_duration(stats.total_duration_ms),
            )
        )

    def _add_to_default_playlist(self, instrumental: bool) -> None:
        """Add the selected original song or instrumental to the default playlist."""
        if self._playlist_service is None:
            return
        selection = self._tree.selection()
        playlist_id = self._playlist_service.get_default_playlist_id()
        if not selection or playlist_id is None:
            messagebox.showinfo(t("playlist.error"), t("library.no_default_playlist"))
            return
        song_id = int(selection[0])
        try:
            if instrumental:
                missing = self._playlist_service.add_instrumentals(playlist_id, [song_id])
                if missing:
                    messagebox.showinfo(
                        t("playlist.error"),
                        t("playlist.no_instrumental").format(count=len(missing)),
                    )
                    return
            else:
                self._playlist_service.add_songs(playlist_id, [song_id])
        except Exception as exc:
            messagebox.showerror(t("playlist.error"), str(exc))
            return
        self.refresh_default_playlist_summary()
        if self._on_playlist_changed is not None:
            self._on_playlist_changed()

    # -- Event handlers ---------------------------------------------------
    def _on_import(self) -> None:
        """Import audio files selected by the user."""
        extensions = self._library_service.get_import_extensions()
        patterns = [f"*.{extension}" for extension in extensions]
        paths = filedialog.askopenfilenames(
            title=t("library.import_title"),
            filetypes=[(t("library.import_supported"), patterns),
                       ("All files", "*.*")],
        )
        if not paths:
            return
        try:
            imported = self._library_service.import_files(list(paths))
        except Exception as exc:
            messagebox.showerror(t("library.import_error"), str(exc))
            return
        skipped = len(paths) - len(imported)
        self._status_var.set(
            t("library.imported").format(n=len(imported), skipped=skipped))
        self._refresh_song_list()

    def _on_import_separated(self) -> None:
        """Import separated tracks from a Demucs output folder (background)."""
        folder = filedialog.askdirectory(
            title=t("library.import_separated_title"),
        )
        if not folder:
            return
        self._status_var.set(t("library.import_separated_title") + "...")
        import threading
        def _run():
            try:
                result = self._library_service.import_separated_tracks(folder)
            except Exception as exc:
                # Python 3 clears ``exc`` after the except block, so bind the
                # message before scheduling the callback on the Tk thread.
                message = str(exc)
                self.after(0, lambda: messagebox.showerror(
                    t("library.import_separated_error"), message))
                return
            self.after(0, lambda: self._status_var.set(
                t("library.import_separated_result").format(
                    matched=result["matched"],
                    imported=result["imported"],
                    skipped=result["skipped"],
                )))
            self.after(0, self._refresh_song_list)
        threading.Thread(target=_run, daemon=True).start()

    def _on_search(self) -> None:
        """Run a search with the current toolbar values."""
        self._refresh_song_list()

    def _on_double_click(self, event: Event) -> None:
        """Show a detail dialog for the double-clicked song."""
        sel = self._tree.selection()
        if not sel:
            return
        try:
            song = self._library_service.get_song(int(sel[0]))
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        detail = (
            f"{t('detail.title')}:  {song.title}\n"
            f"{t('detail.artist')}:  {song.artist}\n"
            f"{t('detail.album')}:  {song.album}\n"
            f"{t('detail.path')}:  {song.file_path}\n"
            f"{t('detail.duration')}:  {format_duration(song.duration_ms)}\n"
            f"{t('detail.format')}:  {song.format}  |  "
            f"{t('detail.bitrate')}:  {song.bitrate_bps} bps\n"
            f"{t('detail.sample_rate')}:  {song.sample_rate_hz} Hz  |  "
            f"{t('detail.channels')}:  {song.channels}\n"
            f"{t('detail.file_size')}:  {song.file_size_bytes} bytes\n"
            f"{t('detail.vocal_removed')}:  "
            f"{t('detail.yes') if song.has_vocal_removed else t('detail.no')}  |  "
            f"{t('detail.normalized')}:  "
            f"{t('detail.yes') if song.is_normalized else t('detail.no')}\n"
            f"{t('detail.tags')}:  "
            f"{', '.join(ti.name for ti in song.tags) or t('detail.none')}"
        )
        messagebox.showinfo(
            t("library.song_detail").format(title=song.title), detail)

    def _on_right_click(self, event: Event) -> None:
        """Show the context menu for the right-clicked row."""
        item = self._tree.identify_row(event.y)
        if item:
            self._tree.selection_set(item)
        if not self._tree.selection():
            return
        song_id = int(self._tree.selection()[0])
        # Reuse one menu widget instead of leaking a new one per right-click.
        if self._context_menu is not None:
            self._context_menu.destroy()
        menu = Menu(self, tearoff=0)
        self._context_menu = menu
        menu.add_command(label=t("library.add_original_to_default"),
                         command=lambda: self._add_to_default_playlist(False))
        menu.add_command(label=t("library.add_instrumental_to_default"),
                         command=lambda: self._add_to_default_playlist(True))
        menu.add_separator()
        menu.add_command(label=t("library.delete"), command=self._on_delete)
        menu.add_command(label=t("library.add_tag"), command=self._on_add_tag)

        # Play Track submenu for songs with separated tracks
        tracks = self._library_service.get_separated_tracks(song_id)
        if tracks:
            play_menu = Menu(menu, tearoff=0)
            for track in tracks:
                play_menu.add_command(
                    label=t("library.play_track_entry").format(
                        track_type=track.track_type),
                    command=lambda p=track.file_path: messagebox.showinfo(
                        t("library.file_path"), p),
                )
            menu.add_cascade(
                label=t("library.play_track"), menu=play_menu)

        menu.post(event.x_root, event.y_root)

    def _on_delete(self) -> None:
        """Delete the selected song after confirmation."""
        sel = self._tree.selection()
        if not sel:
            return
        song_id = int(sel[0])
        try:
            song = self._library_service.get_song(song_id)
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        if not messagebox.askyesno(
            t("library.confirm_delete"),
            t("library.delete_msg").format(title=song.title, artist=song.artist),
        ):
            return
        try:
            self._library_service.delete_song(song_id)
        except Exception as exc:
            messagebox.showerror(t("library.delete_error"), str(exc))
            return
        self._status_var.set(t("library.deleted").format(title=song.title))
        self._refresh_song_list()

    def _on_add_tag(self) -> None:
        """Prompt for a tag name and add it to the selected song."""
        sel = self._tree.selection()
        if not sel:
            return
        song_id = int(sel[0])
        name = simpledialog.askstring(
            t("library.tag_prompt"), t("library.tag_name"), parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        try:
            self._library_service.add_tag(song_id, name)
        except Exception as exc:
            messagebox.showerror(t("library.tag_error"), str(exc))
            return
        self._status_var.set(t("library.tag_added").format(name=name))
        self._refresh_song_list()
