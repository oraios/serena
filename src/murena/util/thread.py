import threading
from collections.abc import Callable
from enum import Enum
from typing import Generic, TypeVar

from sensai.util.string import ToStringMixin


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
    Executes the given function with a timeout

    :param func: the function to execute
    :param timeout: the timeout in seconds
    :param function_name: the name of the function (for error messages)
    :returns: the execution result
    """
    execution_result: ExecutionResult[T] = ExecutionResult()

    def target() -> None:
        try:
            value = func()
            execution_result.set_result_value(value)
        except Exception as e:
            execution_result.set_exception(e)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        timeout_exception = TimeoutException(f"Execution of '{function_name}' timed out after {timeout} seconds.", timeout)
        execution_result.set_timed_out(timeout_exception)

    return execution_result
