import time

import pytest

from murena.task_executor import TaskExecutor


@pytest.fixture
def executor():
    """
    Fixture for a basic MurenaAgent without a project
    """
    return TaskExecutor("TestExecutor")


class Task:
    def __init__(self, delay: float, exception: bool = False):
        self.delay = delay
        self.exception = exception
        self.did_run = False

    def run(self):
        self.did_run = True
        time.sleep(self.delay)
        if self.exception:
            raise ValueError("Task failed")
        return True


def test_task_executor_sequence(executor):
    """
    Tests that a sequence of tasks is executed correctly
    """
    future1 = executor.issue_task(Task(1).run, name="task1")
    future2 = executor.issue_task(Task(1).run, name="task2")
    assert future1.result() is True
    assert future2.result() is True


def test_task_executor_exception(executor):
    """
    Tests that tasks that raise exceptions are handled correctly, i.e. that
      * the exception is propagated,
      * subsequent tasks are still executed.
    """
    future1 = executor.issue_task(Task(1, exception=True).run, name="task1")
    future2 = executor.issue_task(Task(1).run, name="task2")
    have_exception = False
    try:
        assert future1.result()
    except Exception as e:
        assert isinstance(e, ValueError)
        have_exception = True
    assert have_exception
    assert future2.result() is True


def test_task_executor_cancel_current(executor):
    """
    Tests that tasks that are cancelled are handled correctly, i.e. that
      * subsequent tasks are executed as soon as cancellation ensues.
      * the cancelled task raises CancelledError when result() is called.
    """
    start_time = time.time()
    future1 = executor.issue_task(Task(10).run, name="task1")
    future2 = executor.issue_task(Task(1).run, name="task2")
    time.sleep(1)
    future1.cancel()
    assert future2.result() is True
    end_time = time.time()
    assert (end_time - start_time) < 9, "Cancelled task did not stop in time"
    have_cancelled_error = False
    try:
        future1.result()
    except Exception as e:
        assert e.__class__.__name__ == "CancelledError"
        have_cancelled_error = True
    assert have_cancelled_error


def test_task_executor_cancel_future(executor):
    """
    Tests that when a future task is cancelled, it is never run at all
    """
    task1 = Task(10)
    task2 = Task(1)
    future1 = executor.issue_task(task1.run, name="task1")
    future2 = executor.issue_task(task2.run, name="task2")
    time.sleep(1)
    future2.cancel()
    future1.cancel()
    try:
        future2.result()
    except:
        pass
    assert task1.did_run
    assert not task2.did_run


def test_task_executor_cancellation_via_task_info(executor):
    start_time = time.time()
    executor.issue_task(Task(10).run, "task1")
    executor.issue_task(Task(10).run, "task2")
    task_infos = executor.get_current_tasks()
    task_infos2 = executor.get_current_tasks()

    # test expected tasks
    assert len(task_infos) == 2
    assert "task1" in task_infos[0].name
    assert "task2" in task_infos[1].name

    # test task identifiers being stable
    assert task_infos2[0].task_id == task_infos[0].task_id

    # test cancellation
    task_infos[0].cancel()
    time.sleep(0.5)
    task_infos3 = executor.get_current_tasks()
    assert len(task_infos3) == 1  # Cancelled task is gone from the queue
    task_infos3[0].cancel()
    try:
        task_infos3[0].future.result()
    except:
        pass
    end_time = time.time()
    assert (end_time - start_time) < 9, "Cancelled task did not stop in time"
