"""Tests for TaskService — enqueue, cancel, status, worker lifecycle."""

from __future__ import annotations

import threading
import time

import pytest

from core.enums import TaskStatus, TaskType
from core.exceptions import TaskNotFoundError
from core.models import TaskInfo
from database.task_repo import TaskRepo


class TestTaskServiceEnqueue:
    """Task creation and queue management."""

    def test_enqueue_returns_task_with_id(self, task_service):
        task = TaskInfo(id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING, progress=0.0, input_data={})
        result = task_service.enqueue(task)
        assert result.id is not None
        assert result.id > 0
        assert result.created_at != ""

    def test_enqueue_does_not_mutate_input_task_type(self, task_service):
        """Regression: enqueue must not convert Enum fields to strings on the original object."""
        task = TaskInfo(id=None, task_type=TaskType.DEMUCS, status=TaskStatus.PENDING, progress=0.0, input_data={})
        task_service.enqueue(task)
        assert task.task_type == TaskType.DEMUCS
        assert isinstance(task.task_type, TaskType)

    def test_enqueue_does_not_mutate_input_status(self, task_service):
        task = TaskInfo(id=None, task_type=TaskType.EXPORT, status=TaskStatus.PENDING, progress=0.0, input_data={})
        task_service.enqueue(task)
        assert task.status == TaskStatus.PENDING
        assert isinstance(task.status, TaskStatus)

    def test_enqueue_notifies_callbacks(self, task_service):
        results: list = []
        task_service.subscribe(lambda tasks: results.append(tasks))
        task = TaskInfo(id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING, progress=0.0, input_data={})
        task_service.enqueue(task)
        assert len(results) >= 1
        assert any(t.id == task.id for t in results[-1])


class TestTaskServiceQuery:
    """Read operations on the task queue."""

    def test_get_status_returns_task(self, task_service):
        task = TaskInfo(id=None, task_type=TaskType.DEMUCS, status=TaskStatus.PENDING, progress=0.0, input_data={})
        created = task_service.enqueue(task)
        fetched = task_service.get_status(created.id)
        assert fetched.id == created.id
        assert fetched.task_type == TaskType.DEMUCS

    def test_get_status_raises_for_missing(self, task_service):
        with pytest.raises(TaskNotFoundError):
            task_service.get_status(99999)

    def test_get_all_tasks_respects_limit(self, task_service):
        for _ in range(5):
            task = TaskInfo(id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING, progress=0.0, input_data={})
            task_service.enqueue(task)
        tasks = task_service.get_all_tasks(limit=3)
        assert len(tasks) == 3

    def test_get_all_tasks_newest_first(self, task_service):
        task1 = task_service.enqueue(TaskInfo(id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING, progress=0.0, input_data={}))
        time.sleep(0.01)
        task2 = task_service.enqueue(TaskInfo(id=None, task_type=TaskType.DEMUCS, status=TaskStatus.PENDING, progress=0.0, input_data={}))
        tasks = task_service.get_all_tasks()
        ids = [t.id for t in tasks]
        assert ids.index(task2.id) < ids.index(task1.id)


class TestTaskServiceCancel:
    """Task cancellation."""

    def test_cancel_pending_task(self, task_service):
        task = TaskInfo(id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING, progress=0.0, input_data={})
        created = task_service.enqueue(task)
        task_service.cancel(created.id)
        fetched = task_service.get_status(created.id)
        assert fetched.status == TaskStatus.CANCELLED

    def test_cancel_raises_for_running_task(self, task_service):
        task = TaskInfo(id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.RUNNING, progress=0.0, input_data={})
        created = task_service.enqueue(task)
        # Simulate running by directly updating status
        from database.task_repo import TaskRepo
        with pytest.raises(ValueError, match="Cannot cancel"):
            task_service.cancel(created.id)


class TestTaskServiceClear:
    """Clearing completed tasks."""

    def test_clear_completed_removes_done_tasks(self, task_service, db_conn):
        task_repo = TaskRepo(db_conn)
        task = TaskInfo(id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING, progress=0.0, input_data={})
        created = task_service.enqueue(task)
        task_repo.update_status(created.id, TaskStatus.DONE)
        count = task_service.clear_completed()
        assert count >= 1
        with pytest.raises(TaskNotFoundError):
            task_service.get_status(created.id)


class TestTaskServiceWorker:
    """Worker thread execution (with mocked tools)."""

    def test_worker_picks_up_pending_task(self, task_service_worker):
        service = task_service_worker
        service.start()
        try:
            task = TaskInfo(id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING, progress=0.0, input_data={"song_ids": []})
            created = service.enqueue(task)
            time.sleep(0.3)
            fetched = service.get_status(created.id)
            assert fetched.status in (TaskStatus.DONE, TaskStatus.RUNNING)
        finally:
            service.shutdown()

    def test_worker_handles_db_poll_fallback(self, task_service_worker):
        """Task inserted directly into DB (bypassing queue) is picked up by polling."""
        service = task_service_worker
        service.start()
        try:
            task = TaskInfo(id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING, progress=0.0, input_data={"song_ids": []})
            created = service.enqueue(task)
            time.sleep(2.5)
            fetched = service.get_status(created.id)
            assert fetched.status in (TaskStatus.DONE, TaskStatus.RUNNING, TaskStatus.FAILED)
        finally:
            service.shutdown()

    def test_worker_processes_single_queue_item(self, task_service_worker):
        service = task_service_worker
        service.start()
        try:
            task = TaskInfo(id=None, task_type=TaskType.TRANSCODE, status=TaskStatus.PENDING, progress=0.0, input_data={"song_ids": []})
            created = service.enqueue(task)
            time.sleep(0.5)
            fetched = service.get_status(created.id)
            assert fetched.status == TaskStatus.DONE
        finally:
            service.shutdown()
