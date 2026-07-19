"""Audio processing panel — transcode and loudness normalisation."""

from __future__ import annotations

import logging
from tkinter import messagebox

import ttkbootstrap as ttk

from core.formatters import format_duration
from core.i18n import t
from core.models import ProcessConfig, Song
from services.library_service import LibraryService
from services.process_service import ProcessService

logger = logging.getLogger(__name__)

_CH: dict[str, int] = {t("process.mono"): 1, t("process.stereo"): 2}


class ProcessPanel(ttk.Frame):
    """Panel for configuring and submitting batch audio processing tasks.

    Provides song search/selection, transcode settings, loudness
    normalisation controls, and action buttons that create tasks via
    :class:`ProcessService`.  Execution is handled by :class:`TaskService`.
    """

    def __init__(
        self, parent: ttk.Frame,
        process_service: ProcessService,
        library_service: LibraryService,
    ) -> None:
        super().__init__(parent)
        self._process_service = process_service
        self._library_service = library_service
        self._songs: dict[str, Song] = {}
        self._build_ui()
        self._on_search()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_song_selection()
        self._build_transcode_settings()
        self._build_loudness_settings()
        self._build_action_buttons()

    def _build_song_selection(self) -> None:
        f = ttk.LabelFrame(self, text=t("process.song_selection"))
        f.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)

        sf = ttk.Frame(f)
        sf.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        sf.columnconfigure(0, weight=1)

        self._search_var = ttk.StringVar()
        e = ttk.Entry(sf, textvariable=self._search_var)
        e.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        e.bind("<Return>", self._on_search)
        ttk.Button(sf, text=t("library.search"), command=self._on_search,
                   bootstyle="primary").grid(row=0, column=1)

        cols = ("title", "artist", "format", "duration")
        self._tree = ttk.Treeview(
            f, columns=cols, show="headings",
            selectmode="extended", height=10,
        )
        _hdrs = {
            "title": t("library.title"), "artist": t("library.artist"),
            "format": t("library.format_col"), "duration": t("library.duration"),
        }
        for col in cols:
            self._tree.heading(col, text=_hdrs[col])
        self._tree.column("title", width=200, minwidth=100)
        self._tree.column("artist", width=150, minwidth=80)
        self._tree.column("format", width=60, minwidth=50, anchor="center")
        self._tree.column("duration", width=80, minwidth=60, anchor="center")

        sb = ttk.Scrollbar(f, orient="vertical",
                           command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")

    def _build_transcode_settings(self) -> None:
        f = ttk.LabelFrame(self, text=t("process.transcode_settings"))
        f.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        G = {"sticky": "w", "pady": 2}

        ttk.Label(f, text=t("process.output_format")).grid(row=0, column=0, padx=(0, 5), **G)
        self._fmt = ttk.StringVar(value="mp3")
        ttk.Combobox(f, textvariable=self._fmt, values=["mp3", "flac", "wav"],
                     state="readonly", width=8).grid(
            row=0, column=1, padx=(0, 15), **G)

        ttk.Label(f, text=t("process.bitrate")).grid(row=0, column=2, padx=(0, 5), **G)
        self._bitrate = ttk.StringVar(value="320")
        ttk.Combobox(f, textvariable=self._bitrate,
                     values=["128", "192", "256", "320"], state="readonly",
                     width=6).grid(row=0, column=3, padx=(0, 5), **G)
        ttk.Label(f, text="kbps").grid(row=0, column=4, **G)

        ttk.Label(f, text=t("process.sample_rate")).grid(row=1, column=0, padx=(0, 5), **G)
        self._sample_rate = ttk.StringVar(value="44100")
        ttk.Combobox(f, textvariable=self._sample_rate,
                     values=["22050", "44100", "48000"], state="readonly",
                     width=8).grid(row=1, column=1, padx=(0, 15), **G)

        ttk.Label(f, text=t("process.channels")).grid(row=1, column=2, padx=(0, 5), **G)
        self._channels = ttk.StringVar(value=t("process.stereo"))
        ttk.Combobox(f, textvariable=self._channels,
                     values=list(_CH), state="readonly",
                     width=10).grid(row=1, column=3, padx=(0, 5), **G)

    def _build_loudness_settings(self) -> None:
        f = ttk.LabelFrame(self, text=t("process.loudness_title"))
        f.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self._do_norm = ttk.BooleanVar(value=False)
        ttk.Checkbutton(f, text=t("process.normalize"),
                        variable=self._do_norm).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        ttk.Label(f, text=t("process.target_lufs")).grid(
            row=1, column=0, sticky="w", padx=(25, 5))
        self._lufs = ttk.IntVar(value=-16)
        ttk.Spinbox(f, from_=-24, to=-14, textvariable=self._lufs,
                    width=6).grid(row=1, column=1, sticky="w")

        ttk.Label(f, text=t("process.loudnorm_note"),
                  foreground="gray", font=("Helvetica", 9)).grid(
            row=2, column=0, columnspan=2, sticky="w",
            padx=(25, 0), pady=(5, 0))

    def _build_action_buttons(self) -> None:
        f = ttk.Frame(self, padding=(10, 5))
        f.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))
        ttk.Button(f, text=t("process.transcode_btn"),
                   command=self._on_transcode,
                   bootstyle="primary").pack(side="left", padx=(0, 10))
        ttk.Button(f, text=t("process.normalize_btn"),
                   command=self._on_normalize,
                   bootstyle="info").pack(side="left")

    def _on_search(self, _event: object = None) -> None:
        query = self._search_var.get().strip()
        self._songs.clear()
        self._tree.delete(*self._tree.get_children())
        try:
            results = self._library_service.search(query=query, limit=200)
        except Exception as exc:
            logger.exception("Song search failed")
            messagebox.showerror(t("process.search_error"), str(exc), parent=self)
            return
        for song in results:
            if song.id is None:
                continue
            iid = str(song.id)
            self._tree.insert("", "end", iid=iid, values=(
                song.title, song.artist, song.format,
                format_duration(song.duration_ms)))
            self._songs[iid] = song

    def _on_transcode(self) -> None:
        ids = self._selected_ids()
        if not ids:
            messagebox.showwarning(
                t("process.no_selection"),
                t("process.no_selection_msg"),
                parent=self)
            return
        config = ProcessConfig(
            output_format=self._fmt.get(),
            bitrate_bps=int(self._bitrate.get()) * 1000,
            sample_rate_hz=int(self._sample_rate.get()),
            channels=_CH[self._channels.get()],
            target_loudness_lufs=(
                float(self._lufs.get())
                if self._do_norm.get() else None))
        try:
            task = self._process_service.transcode_batch(ids, config)
        except Exception as exc:
            logger.exception("Failed to create transcode task")
            messagebox.showerror(t("process.task_error"), str(exc), parent=self)
            return
        messagebox.showinfo(
            t("process.task_created"),
            t("process.task_created_msg").format(id=task.id),
            parent=self)

    def _on_normalize(self) -> None:
        ids = self._selected_ids()
        if not ids:
            messagebox.showwarning(
                t("process.no_selection"),
                t("process.no_selection_msg"),
                parent=self)
            return
        try:
            task = self._process_service.normalize_loudness_batch(
                ids, float(self._lufs.get()))
        except Exception as exc:
            logger.exception("Failed to create loudness task")
            messagebox.showerror(t("process.task_error"), str(exc), parent=self)
            return
        messagebox.showinfo(
            t("process.task_created"),
            t("process.norm_created_msg").format(id=task.id),
            parent=self)

    def _selected_ids(self) -> list[int]:
        return [int(iid) for iid in self._tree.selection()]
