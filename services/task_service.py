"""Task queue service — enqueue, schedule, monitor on a background thread."""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

from core.enums import TaskStatus, TaskType
from core.exceptions import TaskNotFoundError, ToolExecutionError
from core.models import TaskInfo
from database.playlist_repo import PlaylistRepo
from database.song_repo import SongRepo
from database.separated_track_repo import SeparatedTrackRepo
from database.task_repo import TaskRepo

logger = logging.getLogger(__name__)


class TaskService:
    """Manages the task queue and background worker thread.

    Uses a single worker thread to avoid SQLite concurrent write issues.
    Progress updates are communicated to the GUI via a queue and callbacks.
    The worker thread creates its own SQLite connection so it never shares
    the main-thread connection.
    """

    def __init__(
        self, task_repo: TaskRepo, song_repo=None, ffmpeg=None,
        demucs=None, workspace: Path | None = None,
        playlist_repo=None,
        separated_track_repo=None,
        db_factory: Callable[[], sqlite3.Connection] | None = None,
    ) -> None:
        self._task_repo = task_repo
        self._song_repo = song_repo
        self._ffmpeg = ffmpeg
        self._demucs = demucs
        self._workspace = workspace
        self._playlist_repo = playlist_repo
        self._separated_track_repo = separated_track_repo
        self._db_factory = db_factory
        self._queue: queue.Queue[TaskInfo] = queue.Queue()
        self._callbacks: list[Callable] = []
        self._shutdown_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

    # -- Public API ------------------------------------------------------

    def start(self) -> None:
        """Start the worker thread.  Call once at app startup."""
        if self._worker_thread and self._worker_thread.is_alive():
            logger.warning("Worker thread is already running")
            return
        self._shutdown_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="TaskService-worker", daemon=True,
        )
        self._worker_thread.start()
        logger.info("TaskService worker thread started")

    def shutdown(self) -> None:
        """Gracefully stop the worker.  Waits for the current task to finish."""
        logger.info("Shutting down TaskService worker thread …")
        self._shutdown_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=30)
        logger.info("TaskService shut down complete")

    def enqueue(self, task: TaskInfo) -> TaskInfo:
        """Add a task to the queue.  Returns the task with *id* set."""
        task.progress = 0.0
        task = self._task_repo.insert(task)
        self._queue.put(task)
        logger.info("Enqueued task id=%d type=%s", task.id, task.task_type)
        self._notify_callbacks()
        return task

    def create_task(self, task: TaskInfo) -> TaskInfo:
        """Alias for enqueue to make task creation intent explicit."""
        return self.enqueue(task)

    def get_status(self, task_id: int) -> TaskInfo:
        """Return the current state of a task by id."""
        return self._task_repo.get_by_id(task_id)

    def cancel(self, task_id: int) -> None:
        """Mark a *pending* task as cancelled (raises ValueError otherwise)."""
        task = self._task_repo.get_by_id(task_id)
        if task.status != TaskStatus.PENDING:
            raise ValueError(
                f"Cannot cancel task id={task_id} — status is '{task.status.value}'"
            )
        self._task_repo.update_status(task_id, TaskStatus.CANCELLED)
        logger.info("Cancelled task id=%d", task_id)
        self._notify_callbacks()

    def get_all_tasks(self, limit: int = 50) -> list[TaskInfo]:
        """Return recent tasks, most-recent first, up to *limit*."""
        return self._task_repo.get_all(limit=limit)

    def clear_completed(self) -> int:
        """Delete completed / failed / cancelled tasks.  Returns count."""
        count = self._task_repo.delete_completed()
        logger.info("Cleared %d completed task(s)", count)
        if count:
            self._notify_callbacks()
        return count

    def subscribe(self, callback: Callable) -> None:
        """Register *callback(tasks: list[TaskInfo])* for every status change.
        Called from the worker thread; GUI layers wrap with ``root.after()``."""
        self._callbacks.append(callback)
        logger.debug("Subscribed callback (%d total)", len(self._callbacks))

    # -- Worker loop -------------------------------------------------
    def _worker_loop(self) -> None:
        """Main loop of the background worker thread."""
        logger.debug("Worker loop started")
        if self._db_factory is not None:
            worker_conn = self._db_factory()
            self._worker_task_repo = TaskRepo(worker_conn)
            self._worker_song_repo = SongRepo(worker_conn) if self._song_repo is not None else None
            self._worker_playlist_repo = PlaylistRepo(worker_conn) if self._playlist_repo is not None else None
            self._worker_separated_track_repo = SeparatedTrackRepo(worker_conn) if self._separated_track_repo is not None else None
        else:
            worker_conn = None
            self._worker_task_repo = self._task_repo
            self._worker_song_repo = self._song_repo
            self._worker_playlist_repo = self._playlist_repo
            self._worker_separated_track_repo = self._separated_track_repo

        self._init_executors()

        last_db_poll = 0.0
        try:
            while not self._shutdown_event.is_set():
                try:
                    task = self._queue.get(timeout=0.5)
                    self._process_if_pending(task)
                    continue
                except queue.Empty:
                    pass
                if self._shutdown_event.is_set():
                    break
                now = time.monotonic()
                if now - last_db_poll >= 2.0:
                    last_db_poll = now
                    try:
                        pending = self._worker_task_repo.get_pending()
                        if pending:
                            self._process_if_pending(pending[0])
                    except Exception:
                        logger.exception("Error polling DB for pending tasks")
        finally:
            self._cancel_queued_tasks()
            if worker_conn is not None:
                worker_conn.close()
                logger.debug("Worker DB connection closed")
            self._worker_task_repo = None
            self._worker_song_repo = None
            self._worker_playlist_repo = None
            self._worker_separated_track_repo = None
        logger.debug("Worker loop exited")

    def _cancel_queued_tasks(self) -> None:
        """Cancel tasks still waiting in the queue when the worker stops.

        Without this, a shutdown leaves unstarted PENDING rows in the database
        forever, which shows up as permanent "pending" rows in the task monitor.
        Must run before the worker connection is closed.
        """
        repo = self._worker_task_repo
        if repo is None:
            return
        cancelled = 0
        while True:
            try:
                queued = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                current = repo.get_by_id(queued.id)
            except TaskNotFoundError:
                continue
            if current.status != TaskStatus.PENDING:
                continue
            try:
                repo.update_status(current.id, TaskStatus.CANCELLED)
                cancelled += 1
            except Exception:
                logger.exception("Failed to cancel queued task id=%s", queued.id)
        if cancelled:
            logger.info("Cancelled %d queued task(s) on shutdown", cancelled)

    def _init_executors(self) -> None:
        """Create executors wired to worker-owned repos."""
        from services.executors.demucs_executor import DemucsExecutor
        from services.executors.export_executor import ExportExecutor
        from services.executors.transcode_executor import TranscodeExecutor

        is_shutdown = self._shutdown_event.is_set
        self._transcode_executor = TranscodeExecutor(
            self._worker_song_repo, self._ffmpeg, self._workspace,
            self._worker_task_repo, is_shutdown,
        )
        self._demucs_executor = DemucsExecutor(
            self._worker_song_repo, self._ffmpeg, self._demucs,
            self._workspace, self._worker_task_repo, is_shutdown,
            self._worker_separated_track_repo,
        )
        self._export_executor = ExportExecutor(
            self._worker_playlist_repo, self._ffmpeg, self._workspace,
            self._worker_task_repo,
        )

    def _process_if_pending(self, task: TaskInfo) -> None:
        """Refresh *task* from the DB and execute it if it is still PENDING."""
        try:
            current = self._worker_task_repo.get_by_id(task.id)
        except TaskNotFoundError:
            logger.debug("Task id=%d no longer exists — skipping", task.id)
            return
        if current.status != TaskStatus.PENDING:
            logger.debug("Task id=%d status is '%s' — skipping", task.id, current.status.value)
            return
        logger.info("Processing task id=%d type=%s", current.id, current.task_type.value)
        self._worker_task_repo.update_status(current.id, TaskStatus.RUNNING)
        self._notify_callbacks(self._worker_task_repo)
        try:
            self._execute_task(current)
            # A shutdown during execution means the batch was interrupted
            # mid-way — never report such a task as DONE.  A batch that did
            # finish every item (progress reached 1.0) is still reported as
            # DONE, even if the shutdown flag was set during the bookkeeping.
            if self._shutdown_event.is_set() and current.progress < 1.0:
                self._worker_task_repo.update_status(current.id, TaskStatus.CANCELLED)
                logger.info("Task id=%d cancelled (shutdown in progress)", current.id)
            else:
                self._worker_task_repo.update_status(current.id, TaskStatus.DONE, progress=1.0)
                logger.info("Task id=%d completed successfully", current.id)
        except Exception as exc:
            # Executors raise when an interrupted batch had no successful item
            # ("All N … failed").  If the shutdown flag is already set, this is
            # an interruption, not a failure — report it consistently as
            # CANCELLED instead of FAILED.
            if self._shutdown_event.is_set():
                logger.info("Task id=%d cancelled (interrupted: %s)", current.id, exc)
                self._worker_task_repo.update_status(current.id, TaskStatus.CANCELLED)
            else:
                logger.exception("Task id=%d failed: %s", current.id, exc)
                self._worker_task_repo.update_status(
                    current.id, TaskStatus.FAILED,
                    progress=current.progress, error_msg=str(exc),
                )
        finally:
            self._notify_callbacks(self._worker_task_repo)

    # -- Task execution dispatch -------------------------------------
    def _execute_task(self, task: TaskInfo) -> None:
        """Dispatch execution to the appropriate executor by task type."""
        if task.task_type == TaskType.TRANSCODE:
            self._transcode_executor.execute(task)
        elif task.task_type == TaskType.DEMUCS:
            self._demucs_executor.execute(task)
        elif task.task_type == TaskType.EXPORT:
            self._export_executor.execute(task)
        else:
            raise ToolExecutionError(
                f"Execution not yet implemented for task type: {task.task_type.value}",
            )

    # -- Callback helpers --------------------------------------------
    def _notify_callbacks(self, task_repo: TaskRepo | None = None) -> None:
        """Call every subscribed callback with the full task list.

        *task_repo* must be the repo owned by the calling thread: the worker
        thread passes ``self._worker_task_repo`` so that its own SQLite
        connection is used instead of the main thread's connection.
        """
        if not self._callbacks:
            return
        repo = task_repo or self._task_repo
        try:
            tasks = repo.get_all()
        except Exception:
            logger.exception("Failed to fetch tasks for callback notification")
            return
        for cb in self._callbacks:
            try:
                cb(tasks)
            except Exception:
                logger.exception("Callback raised an exception")
