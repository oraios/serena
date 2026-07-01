import time

import pytest

from serena.task_executor import TaskExecutor


@pytest.fixture
def executor():
    """
    Fixture for a basic SerenaAgent without a project
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


import threading


def test_task_records_started_and_finished_at_on_success():
    task = TaskExecutor.Task(function=lambda: "ok", name="t1", logged=False)
    task.start()
    task.wait_until_done(timeout=2.0)
    assert task.started_at is not None
    assert task.finished_at is not None
    assert task.finished_at >= task.started_at


def test_task_records_finished_at_on_failure():
    def boom() -> str:
        raise RuntimeError("nope")

    task = TaskExecutor.Task(function=boom, name="t2", logged=False)
    task.start()
    task.wait_until_done(timeout=2.0)
    assert task.finished_at is not None
    assert task.future.exception() is not None


def test_task_info_get_duration_and_error_message():
    task_ok = TaskExecutor.Task(function=lambda: "ok", name="t3", logged=False)
    task_ok.start()
    task_ok.wait_until_done(timeout=2.0)
    info_ok = TaskExecutor.TaskInfo.from_task(task_ok, is_running=False)
    assert info_ok.get_duration_ms() is not None
    assert info_ok.get_duration_ms() >= 0
    assert info_ok.get_error_message() is None

    def boom() -> str:
        raise RuntimeError("kaboom")

    task_err = TaskExecutor.Task(function=boom, name="t4", logged=False)
    task_err.start()
    task_err.wait_until_done(timeout=2.0)
    info_err = TaskExecutor.TaskInfo.from_task(task_err, is_running=False)
    assert info_err.get_error_message() is not None
    assert "kaboom" in info_err.get_error_message()


def test_task_info_get_display_name_strips_task_n_prefix():
    task = TaskExecutor.Task(function=lambda: "ok", name="Task-7: find_symbol", logged=False)
    info = TaskExecutor.TaskInfo.from_task(task, is_running=False)
    assert info.get_display_name() == "find_symbol"
    task2 = TaskExecutor.Task(function=lambda: "ok", name="naked-name", logged=False)
    info2 = TaskExecutor.TaskInfo.from_task(task2, is_running=False)
    assert info2.get_display_name() == "naked-name"


def test_finished_at_visible_before_future_done_callback_fires():
    """
    Race-fix regression: if finished_at is set AFTER set_result, a done-callback
    observer may see finished_at == None. We assert the inverse: every done-callback
    observation sees finished_at populated.
    """
    observations: list[bool] = []
    barrier = threading.Event()

    for _ in range(100):
        task = TaskExecutor.Task(function=lambda: "ok", name="race", logged=False)

        def cb(_fut, t=task):
            observations.append(t.finished_at is not None)
            if len(observations) == 100:
                barrier.set()

        task.future.add_done_callback(cb)
        task.start()

    barrier.wait(timeout=10.0)
    assert len(observations) == 100
    assert all(observations), "finished_at was None for one or more done-callback observations"
