"""Background task manager.

Every expensive operation (OCR, indexing, thumbnails, conversion, export)
runs through this manager on a worker pool. The UI subscribes to task
events; nothing blocks the GUI thread and every task is cancellable.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid as uuid_mod
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("omnireader.tasks")


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    id: str
    name: str
    kind: str
    fn: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    state: TaskState = TaskState.QUEUED
    progress: float = 0.0            # 0..1, or -1 for indeterminate
    status_text: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0
    speed: float = 0.0
    eta_sec: float = 0.0
    result: Any = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _future: Optional[Future] = None

    def cancel(self) -> bool:
        """Request cancellation; cooperative tasks poll cancel_event."""
        if self.state in (TaskState.QUEUED, TaskState.RUNNING):
            self.cancel_event.set()
            if self.state == TaskState.QUEUED and self._future is not None:
                self._future.cancel()
                if self._future.cancelled():
                    self.state = TaskState.CANCELLED
            return True
        return False

    def can_retry(self) -> bool:
        return self.state in (TaskState.FAILED, TaskState.CANCELLED)


class TaskManager:
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="or-task")
        self._tasks: dict[str, Task] = {}
        self._lock = threading.RLock()
        self._listeners: list[Callable] = []
        self._shutdown = False

    # -- observer API --------------------------------------------------------
    def add_listener(self, cb: Callable) -> None:
        self._listeners.append(cb)

    def remove_listener(self, cb: Callable) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    def _emit(self, task: Task, event: str) -> None:
        for cb in list(self._listeners):
            try:
                cb(task, event)
            except Exception:
                pass

    # -- submission --------------------------------------------------------
    def submit(self, name: str, kind: str, fn: Callable, *args,
               **kwargs) -> Task:
        task = Task(id=uuid_mod.uuid4().hex[:12], name=name, kind=kind, fn=fn,
                    args=args, kwargs=kwargs)
        with self._lock:
            self._tasks[task.id] = task
        self._emit(task, "queued")
        task._future = self._executor.submit(self._run, task)
        return task

    # -- execution --------------------------------------------------------
    def _run(self, task: Task) -> None:
        if task.cancel_event.is_set():
            task.state = TaskState.CANCELLED
            self._emit(task, "cancelled")
            return
        task.state = TaskState.RUNNING
        task.started_at = time.time()
        self._emit(task, "started")

        def progress_cb(fraction: float, status: str = "") -> None:
            if task.cancel_event.is_set():
                raise _TaskCancelled()
            fraction = max(0.0, min(1.0, fraction))
            task.progress = fraction
            if status:
                task.status_text = status
            elapsed = time.time() - task.started_at
            if fraction > 0.02:
                eta = elapsed / fraction - elapsed
                task.eta_sec = max(0.0, eta)
                task.speed = fraction / elapsed if elapsed > 0 else 0
            self._emit(task, "progress")

        try:
            kwargs = dict(task.kwargs)
            kwargs.setdefault("progress", progress_cb)
            kwargs.setdefault("cancel", task.cancel_event)
            result = task.fn(*task.args, **kwargs)
            if task.cancel_event.is_set():
                # The worker cooperated and noticed cancellation.
                task.state = TaskState.CANCELLED
                task.finished_at = time.time()
                self._emit(task, "cancelled")
                return
            task.result = result
            task.progress = 1.0
            task.state = TaskState.DONE
            task.finished_at = time.time()
            self._emit(task, "done")
        except _TaskCancelled:
            task.state = TaskState.CANCELLED
            task.finished_at = time.time()
            self._emit(task, "cancelled")
        except Exception as e:
            task.state = TaskState.FAILED
            task.error = f"{type(e).__name__}: {e}"
            task.finished_at = time.time()
            logger.error("task %s failed: %s\n%s", task.name, e,
                         traceback.format_exc())
            self._emit(task, "failed")

    # -- queries / control ---------------------------------------------------
    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[Task]:
        with self._lock:
            tasks = list(self._tasks.values())
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._tasks.values()
                       if t.state in (TaskState.QUEUED, TaskState.RUNNING))

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        return task.cancel() if task else False

    def retry(self, task_id: str) -> Optional[Task]:
        task = self._tasks.get(task_id)
        if not task or not task.can_retry():
            return None
        return self.submit(task.name, task.kind, task.fn, *task.args,
                           **task.kwargs)

    def clear_finished(self) -> int:
        with self._lock:
            done_ids = [tid for tid, t in self._tasks.items()
                        if t.state in (TaskState.DONE, TaskState.FAILED,
                                       TaskState.CANCELLED)]
            for tid in done_ids:
                del self._tasks[tid]
            return len(done_ids)

    def shutdown(self, wait: bool = False) -> None:
        self._shutdown = True
        with self._lock:
            for t in self._tasks.values():
                if t.state in (TaskState.QUEUED, TaskState.RUNNING):
                    t.cancel_event.set()
        self._executor.shutdown(wait=wait)


class _TaskCancelled(Exception):
    pass


_global_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    global _global_manager
    if _global_manager is None:
        _global_manager = TaskManager()
    return _global_manager
