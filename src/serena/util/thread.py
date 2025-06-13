import logging
import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import Generic, TypeVar

from sensai.util.string import ToStringMixin

from .async_task_manager import get_global_task_manager

log = logging.getLogger(__name__)


class TimeoutException(Exception):
    def __init__(self, message: str, timeout: float) -> None:
        super().__init__(message)
        self.timeout = timeout


T = TypeVar("T")


class ExecutionResult(Generic[T], ToStringMixin):

    class Status(Enum):
        SUCCESS = "success"
        TIMEOUT = "timeout"
        EXCEPTION = "error"

    def __init__(self) -> None:
        self.result_value: T | None = None
        self.status: ExecutionResult.Status | None = None
        self.exception: Exception | None = None

    def set_result_value(self, value: T) -> None:
        self.result_value = value
        self.status = ExecutionResult.Status.SUCCESS

    def set_timed_out(self, exception: TimeoutException) -> None:
        self.exception = exception
        self.status = ExecutionResult.Status.TIMEOUT

    def set_exception(self, exception: Exception) -> None:
        self.exception = exception
        self.status = ExecutionResult.Status.EXCEPTION


def execute_with_timeout(func: Callable[[], T], timeout: float, function_name: str) -> ExecutionResult[T]:
    """
    Executes the given function with optional timeout

    :param func: the function to execute
    :param timeout: the timeout in seconds, or -1 for no timeout (direct execution)
    :param function_name: the name of the function (for error messages)
    :returns: the execution result
    """
    execution_result: ExecutionResult[T] = ExecutionResult()

    # NO TIMEOUT MODE: Execute directly without threading
    if timeout < 0:
        log.debug(f"TIMEOUT: No timeout mode for '{function_name}' - executing directly")
        try:
            start_time = time.time()
            value = func()
            elapsed = time.time() - start_time
            log.debug(f"TIMEOUT: Direct execution of '{function_name}' completed in {elapsed:.2f}s")
            execution_result.set_result_value(value)
        except Exception as e:
            log.exception(f"TIMEOUT: Direct execution of '{function_name}' failed: {e}")
            execution_result.set_exception(e)
        return execution_result

    # TIMEOUT MODE: Use threading as before
    task_id = f"{function_name}_{time.time()}_{id(threading.current_thread())}"
    log.debug(f"TIMEOUT: Starting execution of '{function_name}' with {timeout}s timeout, task_id={task_id}")

    def target() -> None:
        try:
            log.debug(f"TIMEOUT: Thread started for task_id={task_id}")
            start_time = time.time()
            value = func()
            elapsed = time.time() - start_time
            log.debug(f"TIMEOUT: Thread completed successfully for task_id={task_id} in {elapsed:.2f}s")
            execution_result.set_result_value(value)
        except Exception as e:
            log.exception(f"TIMEOUT: Thread failed for task_id={task_id}: {e}")
            execution_result.set_exception(e)

    thread = threading.Thread(target=target, daemon=True, name=f"timeout-{function_name}-{task_id}")
    thread.start()
    log.debug(f"TIMEOUT: Thread {thread.name} started, waiting {timeout}s for completion")

    thread.join(timeout=timeout)

    if thread.is_alive():
        log.warning(f"TIMEOUT: Thread {thread.name} is still alive after {timeout}s - ABANDONING THREAD!")
        log.warning(f"TIMEOUT: This creates a potential deadlock condition for task_id={task_id}")

        # Try to cancel any async operations through the global task manager
        task_manager = get_global_task_manager()
        try:
            # Look for tasks that might be associated with this function call
            active_task_ids = task_manager.get_active_task_ids()
            cancelled_any = False

            for active_task_id in active_task_ids:
                if function_name in active_task_id or task_id in active_task_id:
                    log.debug(f"TIMEOUT: Attempting to cancel related async task: {active_task_id}")
                    if task_manager.cancel_task(active_task_id):
                        cancelled_any = True

            if cancelled_any:
                log.debug(f"TIMEOUT: Cancelled related async operations for task_id={task_id}")
            else:
                log.debug(f"TIMEOUT: No related async operations found to cancel for task_id={task_id}")

            # Log all active tasks for debugging
            task_manager.log_active_tasks()

        except Exception as e:
            log.error(f"TIMEOUT: Error during async task cancellation for task_id={task_id}: {e}")

        timeout_exception = TimeoutException(f"Execution of '{function_name}' timed out after {timeout} seconds.", timeout)
        execution_result.set_timed_out(timeout_exception)
        log.error(f"TIMEOUT: Returning timeout exception for task_id={task_id}")
    else:
        log.debug(f"TIMEOUT: Thread {thread.name} completed within timeout")

    return execution_result
