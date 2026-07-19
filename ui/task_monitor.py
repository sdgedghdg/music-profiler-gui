"""Task monitor widget — compact status bar + expandable task list."""

from __future__ import annotations

import logging
from typing import Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from core.i18n import t
from core.models import TaskInfo
from services.task_service import TaskService

logger = logging.getLogger(__name__)

_MAX_TREE_ROWS = 10
_STYLE = {"pending": SECONDARY, "running": INFO, "done": SUCCESS, "failed": DANGER, "cancelled": WARNING}
_FG = {SECONDARY: "#6c757d", INFO: "#0d6efd", SUCCESS: "#198754", DANGER: "#dc3545", WARNING: "#fd7e14"}


class TaskMonitor(ttk.Frame):
    """Compact footer widget displaying task queue status.

    Collapsed (default): single status row with counts, optional progress
    bar for the active task, and an expand button.

    Expanded: a Treeview listing recent tasks with colour-coded statuses,
    a right-click context menu for cancelling pending tasks, and a button
    to clear all completed / failed / cancelled tasks.
    """

    def __init__(self, parent: ttk.Frame, task_service: TaskService) -> None:
        super().__init__(parent)
        self._task_service = task_service
        self._expanded = False
        self._progress_visible = False
        self._build_collapsed_view()
        self._build_expanded_view()
        self._expanded_view.pack_forget()
        self._task_service.subscribe(self._on_tasks_changed)
        self._refresh()
        self.after(500, self._auto_refresh)

    # -- Collapsed view --------------------------------------------------------

    def _build_collapsed_view(self) -> None:
        self._collapsed_view = ttk.Frame(self)
        self._collapsed_view.pack(fill=X)
        self._status_label = ttk.Label(self._collapsed_view, text=t("tasks.collapsed").format(pending=0, running=0, done=0))
        self._status_label.pack(side=LEFT, padx=(5, 10))
        self._progress_bar = ttk.Progressbar(self._collapsed_view, mode="determinate", length=120)
        self._current_task_label = ttk.Label(self._collapsed_view, text="", bootstyle=INFO)
        self._expand_btn = ttk.Button(
            self._collapsed_view, text=f"▲ {t('tasks.show')}", command=self._expand,
            bootstyle=(INFO, OUTLINE), width=12,
        )
        self._expand_btn.pack(side=RIGHT, padx=(0, 5))

    def _update_collapsed(self, tasks: list[TaskInfo]) -> None:
        counts = self._count_by_status(tasks)
        self._status_label.configure(text=t("tasks.collapsed").format(
            pending=counts['pending'], running=counts['running'], done=counts['done']))
        running = [t for t in tasks if self._status_str(t) == "running"]
        if running:
            pct = int(running[0].progress * 100)
            self._progress_bar.configure(value=pct)
            self._current_task_label.configure(
                text=t("tasks.processing").format(type=self._type_str(running[0]), pct=pct))
            if not self._progress_visible:
                self._progress_bar.pack(side=LEFT, padx=(0, 5))
                self._current_task_label.pack(side=LEFT, padx=(0, 10))
                self._progress_visible = True
        elif self._progress_visible:
            self._progress_bar.pack_forget()
            self._current_task_label.pack_forget()
            self._progress_visible = False

    # -- Expanded view ---------------------------------------------------------

    def _build_expanded_view(self) -> None:
        self._expanded_view = ttk.Frame(self)
        cols = ("id", "type", "status", "progress", "created")
        self._tree = ttk.Treeview(self._expanded_view, columns=cols, show="headings", height=_MAX_TREE_ROWS)
        for col, label, w in [("id", t("tasks.id"), 40), ("type", t("tasks.type"), 85), ("status", t("tasks.status"), 80),
                               ("progress", t("tasks.progress"), 70), ("created", t("tasks.created"), 140)]:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=w, anchor=CENTER)
        self._tree.pack(fill=X, padx=5, pady=(5, 0))
        for sk, bs in _STYLE.items():
            self._tree.tag_configure(sk, foreground=_FG[bs])
        self._ctx_menu = ttk.Menu(self, tearoff=0)
        self._ctx_menu.add_command(label=t("tasks.cancel"), command=self._cancel_selected)
        self._tree.bind("<Button-3>", self._on_right_click)
        btn_frame = ttk.Frame(self._expanded_view)
        btn_frame.pack(fill=X, padx=5, pady=(5, 5))
        self._clear_btn = ttk.Button(btn_frame, text=t("tasks.clear"),
                                     command=self._clear_completed, bootstyle=(DANGER, OUTLINE))
        self._clear_btn.pack(side=LEFT)
        self._collapse_btn = ttk.Button(btn_frame, text=f"▼ {t('tasks.hide')}",
                                        command=self._collapse, bootstyle=(SECONDARY, OUTLINE), width=10)
        self._collapse_btn.pack(side=RIGHT)

    def _update_treeview(self, tasks: list[TaskInfo]) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)
        for task in tasks[:_MAX_TREE_ROWS]:
            st = self._status_str(task)
            self._tree.insert("", END, iid=str(task.id), values=(
                task.id, self._type_str(task), st.capitalize(),
                f"{int(task.progress * 100)}%",
                task.created_at[:19] if task.created_at else "",
            ), tags=(st,))

    # -- Expand / collapse ----------------------------------------------------

    def _expand(self) -> None:
        self._expanded = True
        self._collapsed_view.pack_forget()
        self._expanded_view.pack(fill=X)
        self._refresh()

    def _collapse(self) -> None:
        self._expanded = False
        self._expanded_view.pack_forget()
        self._collapsed_view.pack(fill=X)
        self._refresh()

    # -- Callbacks ------------------------------------------------------------

    def _on_tasks_changed(self, tasks: list[TaskInfo] | None = None) -> None:
        """Called by TaskService (possibly from worker thread).

        Schedules a refresh on the main thread via ``self.after(0, ...)``
        for thread safety.
        """
        self.after(0, self._refresh)

    def _auto_refresh(self) -> None:
        try:
            self._refresh()
        finally:
            self.after(500, self._auto_refresh)

    def _refresh(self) -> None:
        try:
            tasks: list[TaskInfo] = self._task_service.get_all_tasks(limit=50)
        except Exception:
            logger.exception("Failed to fetch tasks for monitor refresh")
            return
        self._update_collapsed(tasks)
        if self._expanded:
            self._update_treeview(tasks)

    # -- Actions --------------------------------------------------------------

    def _clear_completed(self) -> None:
        try:
            self._task_service.clear_completed()
        except Exception:
            logger.exception("clear_completed failed")
        self._refresh()

    def _cancel_selected(self) -> None:
        if sel := self._tree.selection():
            try:
                self._task_service.cancel(int(sel[0]))
            except ValueError:
                logger.warning("Cannot cancel task %s — not pending", sel[0])
            self._refresh()

    def _on_right_click(self, event: Any) -> None:
        if not (item := self._tree.identify_row(event.y)):
            return
        self._tree.selection_set(item)
        try:
            tasks = self._task_service.get_all_tasks(limit=50)
        except Exception:
            logger.exception("Failed to fetch tasks for context menu")
            return
        task = next((t for t in tasks if t.id == int(item)), None)
        state = NORMAL if (task and self._status_str(task) == "pending") else DISABLED
        self._ctx_menu.entryconfigure(0, state=state)
        self._ctx_menu.tk_popup(event.x_root, event.y_root)

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _status_str(task: TaskInfo) -> str:
        raw = task.status
        return raw.value if hasattr(raw, "value") else str(raw)

    @staticmethod
    def _type_str(task: TaskInfo) -> str:
        raw = task.task_type
        val = raw.value if hasattr(raw, "value") else str(raw)
        return t(f"tasks.type_{val}")

    @staticmethod
    def _count_by_status(tasks: list[TaskInfo]) -> dict[str, int]:
        counts: dict[str, int] = {"pending": 0, "running": 0, "done": 0, "failed": 0, "cancelled": 0}
        for t in tasks:
            s = TaskMonitor._status_str(t)
            counts[s] = counts.get(s, 0) + 1
        return counts
