"""First-run setup wizard for MusicProfiler tool configuration.

Presents a modal dialog where the user can locate external tools (FFmpeg,
FFprobe, Demucs) and have each validated in-place.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Callable

import ttkbootstrap as ttk

from core.i18n import t
from services.config_service import ConfigService

logger = logging.getLogger(__name__)

# -- Tool row definitions ------------------------------------------------
# Each entry: key (matching config.json), optional status

_TOOLS: list[dict[str, Any]] = [
    {"key": "ffmpeg", "optional": False},
    {"key": "ffprobe", "optional": False},
    {"key": "demucs", "optional": True},
]


class SetupWizard(tk.Toplevel):
    """Modal wizard that guides the user through first-run tool configuration.

    Delegates all business logic (validation, persistence) to
    :class:`ConfigService`.
    """

    def __init__(
        self,
        parent: tk.Widget,
        config_service: ConfigService,
        on_complete: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._config = config_service
        self._on_complete = on_complete

        self.title(t("wizard.title"))
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Per-tool widgets
        self._entries: dict[str, ttk.Entry] = {}
        self._status_labels: dict[str, ttk.Label] = {}

        self._build_ui()
        self._center_on_parent(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_finish)

    # ------------------------------------------------------------------ #
    #  UI construction
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        """Create and lay out all widgets."""
        header = ttk.Label(
            self,
            text=t("wizard.header"),
            justify=tk.CENTER,
            font=("Helvetica", 12),
            padding=(20, 15),
        )
        header.pack(fill=tk.X)

        rows_frame = ttk.Frame(self, padding=(20, 5))
        rows_frame.pack(fill=tk.BOTH, expand=True)

        for idx, tool in enumerate(_TOOLS):
            self._build_tool_row(rows_frame, tool, idx)

        # -- bottom bar -------------------------------------------------

        btn_frame = ttk.Frame(self, padding=(20, 15))
        btn_frame.pack(fill=tk.X)

        ttk.Button(
            btn_frame,
            text=t("wizard.finish"),
            command=self._on_finish,
            bootstyle="success",
        ).pack(side=tk.RIGHT, padx=(5, 0))

        # Pre-fill entries for already-configured tools
        for tool in _TOOLS:
            existing = self._config.get_tool_path(tool["key"])
            if existing:
                entry = self._entries[tool["key"]]
                entry.delete(0, tk.END)
                entry.insert(0, existing)

    def _build_tool_row(
        self, parent: ttk.Frame, tool: dict[str, Any], row: int
    ) -> None:
        """Build one row: label | entry | browse | status | [skip]."""
        tool_key: str = tool["key"]
        optional: bool = tool["optional"]

        ttk.Label(parent, text=f"{t(f'wizard.{tool_key}')}:", width=10, anchor=tk.E).grid(
            row=row, column=0, padx=(0, 5), pady=5, sticky=tk.E
        )

        entry = ttk.Entry(parent, width=40)
        entry.grid(row=row, column=1, padx=(0, 5), pady=5, sticky=tk.EW)
        self._entries[tool_key] = entry

        ttk.Button(
            parent,
            text=t("wizard.browse"),
            command=lambda k=tool_key: self._on_browse(k),
        ).grid(row=row, column=2, padx=(0, 5), pady=5)

        status = ttk.Label(parent, text="", width=4)
        status.grid(row=row, column=3, padx=(0, 5), pady=5)
        self._status_labels[tool_key] = status

        if optional:
            ttk.Button(
                parent,
                text=t("wizard.skip"),
                command=lambda k=tool_key: self._on_skip(k),
                bootstyle="secondary",
            ).grid(row=row, column=4, pady=5)

        parent.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------ #
    #  Event handlers
    # ------------------------------------------------------------------ #

    def _on_browse(self, tool_key: str) -> None:
        """Open a file dialog, set the path, and validate immediately."""
        path: str = filedialog.askopenfilename(
            title=f"Locate {tool_key} executable"
        )
        if not path:
            return

        entry = self._entries[tool_key]
        entry.delete(0, tk.END)
        entry.insert(0, path)

        self._config.set_tool_path(tool_key, path)
        self._set_status(tool_key, self._config.validate_tool(tool_key))

    def _on_skip(self, tool_key: str) -> None:
        """Clear an optional tool and mark it as skipped."""
        self._entries[tool_key].delete(0, tk.END)
        self._config.set_tool_path(tool_key, None)
        self._status_labels[tool_key].config(text="—")

    def _on_finish(self) -> None:
        """Validate all tools, warn about missing required tools, then close."""
        # Sync typed paths (in case the user typed without browsing)
        for tool in _TOOLS:
            key = tool["key"]
            raw = self._entries[key].get().strip()
            path = raw if raw else None
            self._config.set_tool_path(key, path)

        # Validate and update status
        results = self._config.validate_tools()
        for tool in _TOOLS:
            key = tool["key"]
            self._set_status(key, results.get(key, False))

        # Warn if required tools are missing
        missing_required = [
            t(f"wizard.{tool['key']}")
            for tool in _TOOLS
            if not tool["optional"] and not results.get(tool["key"], False)
        ]

        if missing_required:
            proceed = messagebox.askyesno(
                t("wizard.missing_title"),
                t("wizard.missing_msg").format(tools="/".join(missing_required)),
                parent=self,
            )
            if not proceed:
                return

        logger.info("Setup wizard completed successfully.")
        self._on_complete()
        self.destroy()

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _set_status(self, tool_key: str, is_valid: bool) -> None:
        """Update the status indicator for a single tool row."""
        lbl = self._status_labels[tool_key]
        path = self._config.get_tool_path(tool_key)

        if is_valid:
            lbl.config(text="✓", foreground="green")
        elif path:
            lbl.config(text="✗", foreground="red")
        else:
            lbl.config(text="—")

    def _center_on_parent(self, parent: tk.Widget) -> None:
        """Position this window centred on its parent."""
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        ww = self.winfo_width()
        wh = self.winfo_height()
        x = px + (pw - ww) // 2
        y = py + (ph - wh) // 2
        self.geometry(f"+{x}+{y}")
