"""Export panel for creating broadcast-ready playlist exports."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from core.formatters import format_duration
from core.exceptions import ExportError
from core.i18n import t
from core.models import ExportConfig, Playlist
from services.export_service import ExportService
from services.playlist_service import PlaylistService
from tools.platform import open_file_explorer

logger = logging.getLogger(__name__)

_DEFAULT_REFERENCE_MINUTES = 25


class ExportPanel(ttk.Frame):
    """Panel for configuring and triggering broadcast file exports."""

    def __init__(
        self, parent: tk.Widget, export_service: ExportService,
        playlist_service: PlaylistService,
    ) -> None:
        super().__init__(parent, padding=10)
        self._export_service = export_service
        self._playlist_service = playlist_service
        self._playlists: list[Playlist] = []
        self._playlist_var = tk.StringVar(value="")
        self._fmt_var = tk.StringVar(value="mp3")
        self._bitrate_var = tk.StringVar(value="320")
        self._sr_var = tk.StringVar(value="44100")
        self._norm_var = tk.BooleanVar(value=True)
        self._ref_var = tk.IntVar(value=25)
        self._remaining_var = tk.StringVar(value="")
        self._selected_id: int | None = None
        self.columnconfigure(0, weight=1)
        self._build_playlist_selection()
        self._build_export_settings()
        self._build_reference_duration()
        self._build_export_actions()
        self._refresh_playlists()
    # -- Playlist selection --------------------------------------------------

    def _build_playlist_selection(self) -> None:
        frame = ttk.LabelFrame(self, text=t("export.playlist"))
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(0, weight=1)
        self._playlist_combo = ttk.Combobox(
            frame, textvariable=self._playlist_var, state="readonly")
        self._playlist_combo.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._playlist_combo.bind("<<ComboboxSelected>>", self._on_playlist_selected)
        self._playlist_combo.bind("<Button-1>", lambda e: self._on_combo_opened())
        ttk.Button(frame, text=t("export.validate"), command=self._on_validate,
                   width=10).grid(row=0, column=1)
        self._info_lbl = ttk.Label(frame, text="", font=("", 9), foreground="gray")
        self._info_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _on_combo_opened(self) -> None:
        """Refresh the playlist list while keeping the visible selection in sync."""
        keep_id = self._selected_id
        self._refresh_playlists()
        if keep_id is None:
            return
        for index, playlist in enumerate(self._playlists, start=1):
            if playlist.id == keep_id:
                self._playlist_combo.current(index)
                return
        # The selected playlist disappeared: clear the stale internal state.
        self._selected_id = None
        self._info_lbl.config(text="")
        self._remaining_var.set("")
        self._export_btn.config(state="disabled")

    def _refresh_playlists(self) -> None:
        self._playlists = self._playlist_service.get_all()
        vals = [t("export.select_playlist")] + [p.name for p in self._playlists]
        self._playlist_combo["values"] = vals
        self._playlist_combo.current(0)

    def _on_playlist_selected(self, event: tk.Event | None = None) -> None:
        idx = self._playlist_combo.current()
        if idx <= 0:
            self._selected_id = None
            self._info_lbl.config(text="")
            self._remaining_var.set("")
            self._export_btn.config(state="disabled")
            return
        playlist = self._playlists[idx - 1]
        self._selected_id = playlist.id
        self._export_btn.config(state="normal")
        stats = self._playlist_service.get_stats(playlist.id)
        ref = self._ref_var.get()
        rem = self._playlist_service.get_remaining_time(playlist.id, ref)
        self._info_lbl.config(text=(
            f"Songs: {stats.song_count}"
            f" | Duration: {format_duration(stats.total_duration_ms)}"
            f" | Remaining to {ref}min: {format_duration(rem)}"))
        self._update_remaining()

    # -- Export settings -----------------------------------------------------

    def _build_export_settings(self) -> None:
        frame = ttk.LabelFrame(self, text=t("export.settings"))
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(1, weight=1)
        for r, (label, var, vals) in enumerate([
            (t("export.output_format"), self._fmt_var, ["mp3", "wav"]),
            (t("export.bitrate"), self._bitrate_var,
             ["128", "192", "256", "320"]),
            (t("export.sample_rate"), self._sr_var,
             ["22050", "44100", "48000"]),
        ]):
            ttk.Label(frame, text=label).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Combobox(frame, textvariable=var, values=vals,
                         state="readonly", width=10).grid(
                row=r, column=1, sticky="w", pady=2, padx=(8, 0))
        r = 3
        ttk.Checkbutton(frame, text=t("export.normalize"),
                        variable=self._norm_var).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(4, 2))
        ttk.Separator(frame, orient="horizontal").grid(
            row=r + 1, column=0, columnspan=3, sticky="ew", pady=(4, 2))
        ttk.Label(frame, text=t("export.coming_soon"), font=("", 8),
                  foreground="gray").grid(
            row=r + 2, column=0, columnspan=3, sticky="w", pady=(2, 0))
        for i, label in enumerate((t("export.crossfade"), t("export.fade_in"), t("export.fade_out"))):
            row = r + 3 + i
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
            e = ttk.Entry(frame, width=12, state="disabled")
            e.insert(0, "0")
            e.grid(row=row, column=1, sticky="w", pady=2, padx=(8, 0))
            ttk.Label(frame, text="ms", font=("", 8),
                      foreground="gray").grid(row=row, column=2, sticky="w", pady=2)

    # -- Reference duration --------------------------------------------------

    def _build_reference_duration(self) -> None:
        frame = ttk.LabelFrame(self, text=t("export.reference_title"))
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        bar = ttk.Frame(frame)
        bar.grid(row=0, column=0, sticky="w")
        ttk.Label(bar, text=t("export.reference")).pack(
            side="left", padx=(0, 6))
        ttk.Spinbox(bar, textvariable=self._ref_var,
                    from_=1, to=120, increment=1, width=5).pack(side="left")
        self._ref_var.trace_add("write", self._on_ref_changed)
        self._remaining_lbl = ttk.Label(
            frame, textvariable=self._remaining_var, font=("", 9))
        self._remaining_lbl.grid(row=1, column=0, sticky="w", pady=(4, 0))

    def _on_ref_changed(self, *args: object) -> None:
        # The spinbox is editable: a partially-typed or empty value must not
        # raise TclError out of the Tk callback.
        try:
            self._ref_var.get()
        except (tk.TclError, ValueError):
            return
        self._update_remaining()
        if self._selected_id is not None:
            self._on_playlist_selected()

    def _update_remaining(self) -> None:
        if self._selected_id is None:
            self._remaining_var.set("")
            return
        try:
            ref = self._ref_var.get()
        except (tk.TclError, ValueError):
            return
        rem = self._playlist_service.get_remaining_time(self._selected_id, ref)
        direction = t("export.under") if rem >= 0 else t("export.over")
        self._remaining_var.set(
            t("export.remaining").format(
                time=format_duration(abs(rem)), direction=direction))

    # -- Validate ------------------------------------------------------------

    def _on_validate(self) -> None:
        if self._selected_id is None:
            messagebox.showwarning(
                t("export.no_playlist"), t("export.no_playlist_msg"))
            return
        playlist = self._playlist_service.get(self._selected_id)
        warnings = self._playlist_service.validate_export(playlist.id)
        if not warnings:
            messagebox.showinfo(
                t("export.validation_ok"),
                t("export.validation_ok_msg"))
        else:
            messagebox.showwarning(
                t("export.validation_warn"),
                "Some files are missing:\n\n" + "\n".join(warnings))

    # -- Export actions ------------------------------------------------------

    def _build_export_actions(self) -> None:
        self._export_btn = ttk.Button(
            self, text=t("export.export_btn"), bootstyle="success",
            command=self._on_export, width=30, state="disabled")
        self._export_btn.grid(row=3, column=0, pady=(0, 8))
        hist = ttk.LabelFrame(self, text=t("export.history"))
        hist.grid(row=4, column=0, sticky="ew")
        hist.columnconfigure(0, weight=1)
        ttk.Label(hist, text=t("export.recent"),
                  font=("", 9), foreground="gray").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Button(hist, text=t("export.open_output"),
                   command=self._open_export_folder).grid(
            row=1, column=0, sticky="w")

    def _on_export(self) -> None:
        if self._selected_id is None:
            messagebox.showwarning(
                t("export.no_playlist"), t("export.no_playlist_msg"))
            return
        try:
            task = self._export_service.export(self._selected_id, ExportConfig(
                output_format=self._fmt_var.get(),
                bitrate_bps=int(self._bitrate_var.get()) * 1000,
                sample_rate_hz=int(self._sr_var.get()),
                reference_duration_minutes=self._ref_value(),
                crossfade_ms=0, fade_in_ms=0, fade_out_ms=0,
                normalize_loudness=self._norm_var.get(),
            ))
            messagebox.showinfo(
                t("export.task_created"),
                t("export.task_created_msg").format(id=task.id),
            )
        except ExportError as exc:
            messagebox.showerror(t("export.error"), str(exc))
        except Exception as exc:  # e.g. the playlist was deleted meanwhile
            logger.exception("Export task creation failed")
            messagebox.showerror(t("export.error"), str(exc))

    def _ref_value(self) -> int:
        """Read the reference duration, tolerating an emptied spinbox."""
        try:
            value = self._ref_var.get()
        except (tk.TclError, ValueError):
            value = _DEFAULT_REFERENCE_MINUTES
            self._ref_var.set(value)
        return value if value > 0 else _DEFAULT_REFERENCE_MINUTES

    def _open_export_folder(self) -> None:
        d = self._export_service.get_export_path("_", "mp3").parent
        d.mkdir(parents=True, exist_ok=True)
        open_file_explorer(str(d))
