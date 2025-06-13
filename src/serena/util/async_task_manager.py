"""
AsyncTaskManager for tracking and cancelling async operations during timeouts.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    """Information about a tracked async task"""

    task: asyncio.Task
    function_name: str
    created_at: float
    thread_name: str


class AsyncTaskManager:
    """
    Manages async tasks that can be cancelled when timeouts occur.
    Thread-safe for use across multiple timeout threads.
    """

    def __init__(self) -> None:
        self._active_tasks: dict[str, TaskInfo] = {}
        self._lock = threading.Lock()
        self.logger = logging.getLogger(f"{__name__}.AsyncTaskManager")

    def register_task(self, task_id: str, task: asyncio.Task, function_name: str) -> None:
        """Register an async task for potential cancellation"""
        with self._lock:
            task_info = TaskInfo(
                task=task, function_name=function_name, created_at=time.time(), thread_name=threading.current_thread().name
            )
            self._active_tasks[task_id] = task_info
            self.logger.debug(
                f"ASYNC_MGR: Registered task {task_id} for {function_name}, "
                f"thread={task_info.thread_name}, total_active={len(self._active_tasks)}"
            )

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a specific task and remove it from tracking"""
        with self._lock:
            if task_id in self._active_tasks:
                task_info = self._active_tasks[task_id]
                self.logger.warning(f"ASYNC_MGR: Cancelling task {task_id} ({task_info.function_name}) from thread {task_info.thread_name}")

                if not task_info.task.done():
                    task_info.task.cancel()
                    self.logger.debug(f"ASYNC_MGR: Sent cancel signal to task {task_id}")
                else:
                    self.logger.debug(f"ASYNC_MGR: Task {task_id} already done, no cancellation needed")

                del self._active_tasks[task_id]
                self.logger.debug(f"ASYNC_MGR: Removed task {task_id}, remaining_active={len(self._active_tasks)}")
                return True
            else:
                self.logger.warning(f"ASYNC_MGR: Task {task_id} not found for cancellation")
                return False

    def cancel_all_tasks(self) -> int:
        """Emergency cleanup - cancel all active tasks"""
        with self._lock:
            task_count = len(self._active_tasks)
            if task_count == 0:
                self.logger.debug("ASYNC_MGR: No active tasks to cancel")
                return 0

            self.logger.warning(f"ASYNC_MGR: Emergency cancellation of {task_count} active tasks")

            cancelled_count = 0
            for task_id, task_info in list(self._active_tasks.items()):
                if not task_info.task.done():
                    task_info.task.cancel()
                    cancelled_count += 1
                    self.logger.debug(f"ASYNC_MGR: Emergency cancelled task {task_id}")

            self._active_tasks.clear()
            self.logger.warning(f"ASYNC_MGR: Emergency cancellation complete, cancelled {cancelled_count} tasks")
            return cancelled_count

    def cleanup_completed_tasks(self) -> int:
        """Remove completed/cancelled tasks from tracking"""
        with self._lock:
            completed_tasks = []
            for task_id, task_info in self._active_tasks.items():
                if task_info.task.done():
                    completed_tasks.append(task_id)

            for task_id in completed_tasks:
                task_info = self._active_tasks[task_id]
                del self._active_tasks[task_id]
                self.logger.debug(f"ASYNC_MGR: Cleaned up completed task {task_id} ({task_info.function_name})")

            if completed_tasks:
                self.logger.debug(f"ASYNC_MGR: Cleaned up {len(completed_tasks)} completed tasks")

            return len(completed_tasks)

    def get_active_task_count(self) -> int:
        """Get the number of active tasks"""
        with self._lock:
            return len(self._active_tasks)

    def get_active_task_ids(self) -> set[str]:
        """Get the IDs of all active tasks"""
        with self._lock:
            return set(self._active_tasks.keys())

    def log_active_tasks(self) -> None:
        """Log information about all active tasks"""
        with self._lock:
            if not self._active_tasks:
                self.logger.debug("ASYNC_MGR: No active tasks")
                return

            self.logger.debug(f"ASYNC_MGR: Active tasks ({len(self._active_tasks)}):")
            for task_id, task_info in self._active_tasks.items():
                age = time.time() - task_info.created_at
                status = "done" if task_info.task.done() else "running"
                self.logger.debug(
                    f"  {task_id}: {task_info.function_name}, age={age:.1f}s, status={status}, thread={task_info.thread_name}"
                )

    def get_old_tasks(self, max_age_seconds: float = 300) -> dict[str, TaskInfo]:
        """Get tasks older than the specified age (for debugging)"""
        with self._lock:
            old_tasks = {}
            current_time = time.time()

            for task_id, task_info in self._active_tasks.items():
                age = current_time - task_info.created_at
                if age > max_age_seconds:
                    old_tasks[task_id] = task_info

            if old_tasks:
                self.logger.warning(f"ASYNC_MGR: Found {len(old_tasks)} tasks older than {max_age_seconds}s")

            return old_tasks


# Global instance for use across the application
_global_task_manager: AsyncTaskManager | None = None


def get_global_task_manager() -> AsyncTaskManager:
    """Get the global AsyncTaskManager instance"""
    global _global_task_manager  # noqa: PLW0603
    if _global_task_manager is None:
        _global_task_manager = AsyncTaskManager()
    return _global_task_manager


def reset_global_task_manager() -> None:
    """Reset the global AsyncTaskManager (useful for testing)"""
    global _global_task_manager  # noqa: PLW0603
    if _global_task_manager is not None:
        _global_task_manager.cancel_all_tasks()
    _global_task_manager = AsyncTaskManager()
