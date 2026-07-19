"""Task repository."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

from core.enums import TaskStatus, TaskType
from core.exceptions import TaskNotFoundError
from core.models import TaskInfo

logger = logging.getLogger(__name__)


def _row_to_task(row: sqlite3.Row) -> TaskInfo:
    """Convert a sqlite3.Row to a TaskInfo dataclass."""
    input_data: dict | None = None
    raw_input = row["input_data"]
    if raw_input:
        try:
            input_data = json.loads(raw_input)
        except (json.JSONDecodeError, TypeError):
            input_data = {}

    output_data: dict | None = None
    raw_output = row["output_data"]
    if raw_output:
        try:
            output_data = json.loads(raw_output)
        except (json.JSONDecodeError, TypeError):
            output_data = None

    return TaskInfo(
        id=row["id"],
        task_type=TaskType(row["task_type"]),
        status=TaskStatus(row["status"]),
        progress=row["progress"],
        input_data=input_data,
        output_data=output_data,
        error_msg=row["error_msg"],
        created_at=row["created_at"],
        started_at=row["started_at"] or "",
        finished_at=row["finished_at"] or "",
    )


class TaskRepo:
    """Repository for TaskInfo database operations."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialise with a shared SQLite connection."""
        self._conn = conn

    # -- CRUD ----------------------------------------------------------------

    def insert(self, task: TaskInfo) -> TaskInfo:
        """Insert a new task and return it with id and created_at set."""
        logger.debug("Inserting task type=%s", task.task_type)
        now = datetime.now(timezone.utc).isoformat()
        input_json = json.dumps(task.input_data) if task.input_data else "{}"
        output_json = (
            json.dumps(task.output_data) if task.output_data else None
        )
        task_type = task.task_type.value if isinstance(task.task_type, TaskType) else str(task.task_type)
        status = task.status.value if isinstance(task.status, TaskStatus) else str(task.status or "pending")
        cursor = self._conn.execute(
            "INSERT INTO tasks (task_type, status, progress, input_data, "
            "output_data, error_msg, created_at, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_type,
                status,
                task.progress,
                input_json,
                output_json,
                task.error_msg,
                now,
                task.started_at or None,
                task.finished_at or None,
            ),
        )
        self._conn.commit()
        task.id = cursor.lastrowid
        task.created_at = now
        return task

    def update_status(
        self,
        task_id: int,
        status: TaskStatus,
        progress: float | None = None,
        error_msg: str | None = None,
    ) -> None:
        """Update task status and optionally progress/error_msg.

        Sets *started_at* when transitioning to RUNNING.
        Sets *finished_at* when transitioning to DONE, FAILED, or CANCELLED.

        Raises:
            TaskNotFoundError: If the task does not exist.
        """
        logger.debug(
            "Updating task id=%d status=%s progress=%s",
            task_id, status.value, progress,
        )
        now = datetime.now(timezone.utc).isoformat()

        updates: list[str] = ["status = ?"]
        params: list = [status.value]

        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)

        if error_msg is not None:
            updates.append("error_msg = ?")
            params.append(error_msg)

        if status == TaskStatus.RUNNING:
            updates.append("started_at = ?")
            params.append(now)
        elif status in (
            TaskStatus.DONE,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ):
            updates.append("finished_at = ?")
            params.append(now)

        set_clause = ", ".join(updates)
        params.append(task_id)

        cursor = self._conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            params,
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            raise TaskNotFoundError(task_id)

    def update_output(self, task_id: int, output_data: dict) -> None:
        """Update the output_data for a task.

        Raises:
            TaskNotFoundError: If the task does not exist.
        """
        logger.debug("Updating output for task id=%d", task_id)
        cursor = self._conn.execute(
            "UPDATE tasks SET output_data = ? WHERE id = ?",
            (json.dumps(output_data), task_id),
        )
        self._conn.commit()
        if cursor.rowcount == 0:
            raise TaskNotFoundError(task_id)

    def get_by_id(self, task_id: int) -> TaskInfo:
        """Get a task by id.

        Raises:
            TaskNotFoundError: If the task is not found.
        """
        logger.debug("Getting task by id=%d", task_id)
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        if row is None:
            raise TaskNotFoundError(task_id)
        return _row_to_task(row)

    def get_pending(self) -> list[TaskInfo]:
        """Return all pending tasks, ordered by created_at ASC."""
        logger.debug("Getting pending tasks")
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE status='pending' "
            "ORDER BY created_at ASC"
        ).fetchall()
        return [_row_to_task(row) for row in rows]

    def get_all(self, limit: int = 50) -> list[TaskInfo]:
        """Return all tasks, most recent first, up to *limit*."""
        logger.debug("Getting all tasks, limit=%d", limit)
        rows = self._conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_task(row) for row in rows]

    def delete_completed(self) -> int:
        """Delete all done, failed, or cancelled tasks.

        Returns:
            The number of rows deleted.
        """
        logger.debug("Deleting completed tasks")
        cursor = self._conn.execute(
            "DELETE FROM tasks WHERE status IN ('done', 'failed', 'cancelled')"
        )
        self._conn.commit()
        return cursor.rowcount
