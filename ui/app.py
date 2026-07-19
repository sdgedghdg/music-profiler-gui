"""Main application window for MusicProfiler."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path

import ttkbootstrap as ttk

from core.i18n import t
from database.connection import get_connection
from database.migrations import run_migrations
from database.playlist_repo import PlaylistRepo
from database.separated_track_repo import SeparatedTrackRepo
from database.song_repo import SongRepo
from database.task_repo import TaskRepo
from services.config_service import ConfigService
from services.demucs_service import DemucsService
from services.export_service import ExportService
from services.library_service import LibraryService
from services.playlist_service import PlaylistService
from services.process_service import ProcessService
from services.task_service import TaskService
from tools.base import ToolRunner
from tools.demucs import Demucs
from tools.ffmpeg import FFmpeg
from tools.ffprobe import FFprobe
from tools.ncm import NcmDecryptor
from ui.demucs_panel import DemucsPanel
from ui.export_panel import ExportPanel
from ui.library_panel import LibraryPanel
from ui.playlist_panel import PlaylistPanel
from ui.process_panel import ProcessPanel
from ui.setup_wizard import SetupWizard
from ui.task_monitor import TaskMonitor

logger = logging.getLogger(__name__)

_WORKSPACE_SUBDIRS: tuple[str, ...] = (
    "demucs_output",
    "export",
    "processed",
    "temp",
)


class MusicProfilerApp:
    """Main application window.

    Creates the root window, initialises all services, builds the tabbed UI,
    and manages the application lifecycle (startup and shutdown).
    """

    def __init__(self) -> None:
        # ---- 1. Root window ------------------------------------------------
        self.root = ttk.Window(
            themename="darkly", title=t("app.title"), size=(1200, 800)
        )

        # ---- 2. Configuration ----------------------------------------------
        self.config_service = ConfigService()
        tools_valid = self.config_service.validate_tools()

        if (
            not tools_valid.get("ffmpeg", False)
            or not tools_valid.get("ffprobe", False)
        ):
            wizard = SetupWizard(
                self.root, self.config_service, on_complete=lambda: None
            )
            wizard.wait_window()

        # ---- 3. Database ---------------------------------------------------
        db_path = Path.home() / ".musicprofiler" / "musicprofiler.db"
        self.conn = get_connection(db_path)
        run_migrations(self.conn)
        self.song_repo = SongRepo(self.conn)
        self.playlist_repo = PlaylistRepo(self.conn)
        self.task_repo = TaskRepo(self.conn)
        self.separated_track_repo = SeparatedTrackRepo(self.conn)

        # ---- 4. Tool runners -----------------------------------------------
        def _make_runner(tool_name: str) -> ToolRunner | None:
            path = self.config_service.get_tool_path(tool_name)
            return ToolRunner(path) if path else None

        ffmpeg_runner = _make_runner("ffmpeg")
        ffprobe_runner = _make_runner("ffprobe")
        demucs_runner = _make_runner("demucs")

        # ---- 5. Services ---------------------------------------------------
        workspace = self.config_service.get_workspace()
        for sub in _WORKSPACE_SUBDIRS:
            (workspace / sub).mkdir(parents=True, exist_ok=True)
        (workspace / "imported").mkdir(parents=True, exist_ok=True)

        self.task_service = TaskService(
            self.task_repo,
            self.song_repo,
            FFmpeg(ffmpeg_runner),
            Demucs(demucs_runner) if demucs_runner else None,
            workspace,
            playlist_repo=self.playlist_repo,
            separated_track_repo=self.separated_track_repo,
            db_factory=lambda: get_connection(db_path),
        )
        self.playlist_service = PlaylistService(
            self.playlist_repo,
            self.song_repo,
            self.separated_track_repo,
            self.config_service,
        )
        self.library_service = LibraryService(
            self.song_repo, FFprobe(ffprobe_runner), NcmDecryptor(), workspace,
            separated_track_repo=self.separated_track_repo,
        )
        self.process_service = ProcessService(
            self.song_repo, self.task_service,
        )
        self.demucs_service = DemucsService(
            self.song_repo,
            self.task_service,
            Demucs(demucs_runner) if demucs_runner else None,
            FFmpeg(ffmpeg_runner),
            workspace,
        )
        self.export_service = ExportService(
            self.playlist_repo, self.task_service, FFmpeg(ffmpeg_runner), workspace,
        )

        # ---- 6. UI layout --------------------------------------------------
        menu_bar = tk.Menu(self.root)
        settings_menu = tk.Menu(menu_bar, tearoff=False)
        settings_menu.add_command(
            label=t("app.configure_tools"), command=self._open_tool_setup,
        )
        menu_bar.add_cascade(label=t("app.settings"), menu=settings_menu)
        self.root.config(menu=menu_bar)

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))

        self.library_panel = LibraryPanel(
            notebook,
            self.library_service,
            self.task_service,
            self.playlist_service,
            on_playlist_changed=self._refresh_playlist_panel,
        )
        notebook.add(self.library_panel, text=t("tab.library"))

        self.process_panel = ProcessPanel(
            notebook, self.process_service, self.library_service,
        )
        notebook.add(self.process_panel, text=t("tab.process"))

        self.demucs_panel = DemucsPanel(
            notebook, self.demucs_service, self.library_service,
        )
        notebook.add(self.demucs_panel, text=t("tab.demucs"))

        self.playlist_panel = PlaylistPanel(
            notebook,
            self.playlist_service,
            self.library_service,
            on_default_playlist_changed=self.library_panel.refresh_default_playlist_summary,
        )
        notebook.add(self.playlist_panel, text=t("tab.playlists"))

        self.export_panel = ExportPanel(
            notebook, self.export_service, self.playlist_service,
        )
        notebook.add(self.export_panel, text=t("tab.export"))

        self.task_monitor = TaskMonitor(self.root, self.task_service)
        self.task_monitor.pack(fill=tk.X, padx=5, pady=5)

        # ---- 7. Start worker and register shutdown -------------------------
        self.task_service.start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        logger.info("MusicProfiler ready.")

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    def _refresh_playlist_panel(self) -> None:
        """Refresh the playlist panel after a library quick-add."""
        self.playlist_panel.refresh()

    def _open_tool_setup(self) -> None:
        """Open the external tool configuration wizard."""
        SetupWizard(self.root, self.config_service, lambda: None).wait_window()

    def _on_close(self) -> None:
        """Gracefully shut down services and close the database."""
        logger.info("Shutting down …")
        self.task_service.shutdown()
        self.conn.close()
        self.root.destroy()

    def run(self) -> None:
        """Start the Tkinter main loop."""
        self.root.mainloop()
