"""Demucs panel for vocal/accompaniment separation."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox

import ttkbootstrap as ttk

from core.exceptions import ToolNotFoundError
from core.formatters import format_duration
from core.i18n import t
from core.models import Song, TaskInfo
from services.config_service import ConfigService
from services.demucs_service import DemucsService
from services.library_service import LibraryService
from tools.platform import open_file_explorer

logger = logging.getLogger(__name__)

_MODELS = [
    ("htdemucs (balanced)", "htdemucs"),
    ("htdemucs_ft (fine-tuned)", "htdemucs_ft"),
    ("htdemucs_6s (6-source)", "htdemucs_6s"),
]
_COL_SPECS = [
    ("title", t("library.title"), 200, tk.W),
    ("artist", t("library.artist"), 150, tk.W),
    ("format", t("library.format_col"), 60, tk.CENTER),
    ("duration", t("library.duration"), 80, tk.CENTER),
    ("vocal_removed", t("library.vocal_removed"), 110, tk.CENTER),
]


class DemucsPanel(ttk.Frame):
    """Panel for vocal separation using Demucs."""

    def __init__(
        self,
        parent: tk.Widget,
        demucs_service: DemucsService,
        library_service: LibraryService,
        config_service: ConfigService | None = None,
        on_task_created: Callable[[TaskInfo], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._demucs_service = demucs_service
        self._library = library_service
        self._config = config_service
        self._on_task_created = on_task_created
        self._model_var = ttk.StringVar(value="htdemucs")
        self._hide_processed_var = ttk.BooleanVar(value=False)
        self._search_var = ttk.StringVar()
        self._song_map: dict[str, Song] = {}
        self._result_song_map: dict[str, Song] = {}
        self._build_ui()
        self._on_search()

    def _build_ui(self) -> None:
        bar = ttk.Frame(self, padding=(10, 10, 10, 5))
        bar.pack(fill=tk.X)
        ttk.Label(bar, text=t("demucs.search")).pack(side=tk.LEFT)
        e = ttk.Entry(bar, textvariable=self._search_var, width=40)
        e.pack(side=tk.LEFT, padx=(5, 5))
        e.bind("<Return>", lambda _e: self._on_search())
        ttk.Button(bar, text=t("demucs.search_btn"), command=self._on_search).pack(side=tk.LEFT)

        tf = ttk.Frame(self, padding=(10, 5))
        tf.pack(fill=tk.BOTH, expand=True)
        cols = tuple(c[0] for c in _COL_SPECS)
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="extended")
        for col, hdr, w, a in _COL_SPECS:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w, anchor=a)
        sb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        self._tree.bind("<Double-1>",
                        lambda _e: self._show_results_for(self._tree, self._song_map))
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._update_separate_btn())

        ctrl = ttk.Frame(self, padding=(10, 5))
        ctrl.pack(fill=tk.X)
        ttk.Button(ctrl, text=t("demucs.select_all"),
                   command=lambda: (self._tree.selection_set(self._tree.get_children()),
                                    self._update_separate_btn()),
                   ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(ctrl, text=t("demucs.deselect_all"),
                   command=lambda: (self._tree.selection_remove(*self._tree.selection()),
                                    self._update_separate_btn()),
                   ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(ctrl, text=t("demucs.hide_processed"),
                        variable=self._hide_processed_var,
                        command=self._on_search).pack(side=tk.LEFT)
        ttk.Button(ctrl, text=t("demucs.refresh"), command=self._on_search,
                   bootstyle="secondary-outline").pack(side=tk.RIGHT)

        lf = ttk.LabelFrame(self, text=t("demucs.model_title"))
        lf.pack(fill=tk.X, padx=10, pady=(5, 5))
        for text, value in _MODELS:
            ttk.Radiobutton(lf, text=text, variable=self._model_var, value=value).pack(
                anchor=tk.W, padx=5)
        ttk.Label(lf, text=t("demucs.model_note"),
                  foreground="gray", padding=(5, 10, 5, 0)).pack(anchor=tk.W)

        af = ttk.Frame(self, padding=(10, 10))
        af.pack(fill=tk.X)
        self._separate_btn = ttk.Button(af, text=t("demucs.separate_btn"), command=self._on_separate,
                                        bootstyle="primary", padding=(20, 10))
        self._separate_btn.pack(fill=tk.X)
        self._update_separate_btn()

        lf2 = ttk.LabelFrame(self, text=t("demucs.results_title"))
        lf2.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))
        self._results_tree = ttk.Treeview(lf2, columns=("song", "status"),
                                          show="headings", height=4)
        self._results_tree.heading("song", text=t("demucs.results_song"))
        self._results_tree.heading("status", text=t("demucs.results_status"))
        self._results_tree.column("song", width=300)
        self._results_tree.column("status", width=100, anchor=tk.CENTER)
        self._results_tree.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        self._results_tree.bind("<Double-1>",
                                lambda _e: self._show_results_for(
                                    self._results_tree, self._result_song_map))
        self._results_tree.bind("<Button-3>", self._on_results_right_click)
        ttk.Button(lf2, text=t("demucs.open_output"), command=self._on_open_output,
                   bootstyle="secondary-outline").pack(fill=tk.X)

    def _on_search(self) -> None:
        hv: bool | None = False if self._hide_processed_var.get() else None
        self._load_songs(self._library.search(
            query=self._search_var.get().strip(), has_vocal_removed=hv))

    def _load_songs(self, songs: list[Song]) -> None:
        self._tree.delete(*self._tree.get_children())
        self._song_map.clear()
        for song in songs:
            iid = str(song.id)
            self._song_map[iid] = song
            self._tree.insert("", tk.END, iid=iid, values=(
                song.title, song.artist, song.format.upper(),
                format_duration(song.duration_ms), "✓" if song.has_vocal_removed else ""))
        self._update_separate_btn()

    def _on_separate(self) -> None:
        if not (ids := self._get_selected_ids()):
            return messagebox.showwarning(
                t("demucs.no_selection"), t("demucs.no_selection_msg"))
        try:
            task = self._demucs_service.separate(ids, model=self._model_var.get())
        except ToolNotFoundError as exc:
            messagebox.showerror(t("demucs.unavailable"), str(exc))
            return
        except Exception as exc:
            logger.exception("Failed to create demucs task")
            messagebox.showerror(t("demucs.unavailable"), str(exc))
            return
        for sid in ids:
            song = self._song_map.get(str(sid))
            if song:
                key = f"res_{sid}"
                self._result_song_map[key] = song
                self._results_tree.insert("", tk.END, iid=key, values=(
                    f"{song.artist} - {song.title}", "Pending"))
        if self._on_task_created:
            self._on_task_created(task)
        messagebox.showinfo(t("process.task_created"),
                            t("demucs.task_created").format(id=task.id))

    def _on_open_output(self) -> None:
        ws = self._config.get_workspace() if self._config else Path.cwd() / "workspace"
        path = ws / "demucs_output"
        path.mkdir(parents=True, exist_ok=True)
        try:
            open_file_explorer(path)
        except Exception:
            logger.exception("Failed to open output folder")
            messagebox.showerror("Error", f"Could not open: {path}")

    def _on_results_right_click(self, event: tk.Event) -> None:
        item = self._results_tree.identify_row(event.y)
        if not item:
            return
        song = self._result_song_map.get(item)
        if song is None:
            return
        paths = self._demucs_service.get_result_paths(song)
        menu = tk.Menu(self, tearoff=0)
        if paths:
            menu.add_command(label=t("demucs.play_vocal"),
                             command=lambda p=paths["vocals"]: messagebox.showinfo(
                                 t("demucs.play_vocal"), f"File: {p}"))
            menu.add_command(label=t("demucs.play_inst"),
                             command=lambda p=paths["inst"]: messagebox.showinfo(
                                 t("demucs.play_inst"), f"File: {p}"))
        else:
            menu.add_command(label="Not yet processed", state=tk.DISABLED)
        menu.tk_popup(event.x_root, event.y_root)

    def _show_results_for(self, tree: ttk.Treeview, song_map: dict[str, Song]) -> None:
        sel = tree.selection()
        if not sel:
            return
        song = song_map.get(sel[0])
        if song is None:
            return
        paths = self._demucs_service.get_result_paths(song)
        if paths:
            messagebox.showinfo(f"Results — {song.title}",
                                f"Vocal: {paths['vocals']}\nInstrumental: {paths['inst']}")
        else:
            messagebox.showinfo(song.title,
                                "This song has not been processed with Demucs yet.")

    def _get_selected_ids(self) -> list[int]:
        return [int(i) for i in self._tree.selection() if i.lstrip("-").isdigit()]

    def _update_separate_btn(self) -> None:
        has_sel = bool(self._get_selected_ids())
        configured = True
        if self._config is not None:
            configured = bool(self._config.get_tool_path("demucs"))
        self._separate_btn.configure(
            state=tk.NORMAL if (has_sel and configured) else tk.DISABLED)
