from collections.abc import Callable
from types import SimpleNamespace

from serena.dashboard import SerenaDashboardAPI
from solidlsp.ls_config import LanguageServerId


class _DummyMemoryLogHandler:
    def get_log_messages(self, from_idx: int = 0):  # pragma: no cover - simple stub
        return SimpleNamespace(messages=[], max_idx=-1)

    def clear_log_messages(self) -> None:  # pragma: no cover - simple stub
        pass


class _DummyAgent:
    def __init__(self, project: SimpleNamespace | None) -> None:
        self._project = project

    def register_config_changed_callback(self, callback: Callable[[], None]) -> None:
        pass

    def execute_task(self, func, *, logged: bool | None = None, name: str | None = None):
        del logged, name
        return func()

    def get_active_project(self):
        return self._project


def _make_dashboard(project_languages: list[LanguageServerId] | None) -> SerenaDashboardAPI:
    project = None
    if project_languages is not None:
        project = SimpleNamespace(project_config=SimpleNamespace(language_servers=project_languages))
    agent = _DummyAgent(project)
    return SerenaDashboardAPI(memory_log_handler=_DummyMemoryLogHandler(), tool_names=[], agent=agent, tool_usage_stats=None)


def test_available_languages_include_experimental_when_no_active_project():
    dashboard = _make_dashboard(project_languages=None)
    response = dashboard._get_available_languages()
    expected = sorted(lang.value for lang in LanguageServerId.iter_all(include_experimental=True))
    assert response.languages == expected


def test_available_languages_exclude_project_languages():
    dashboard = _make_dashboard(project_languages=[LanguageServerId.PYTHON, LanguageServerId.MARKDOWN])
    response = dashboard._get_available_languages()
    available = set(response.languages)
    assert LanguageServerId.PYTHON.value not in available
    assert LanguageServerId.MARKDOWN.value not in available
    # ensure experimental languages remain available for selection
    assert LanguageServerId.ANSIBLE.value in available


def _viewer_process_spawning_grandchild(pid_queue) -> None:
    """Stand-in for the dashboard viewer: spawns a real grandchild (like a WebView2 subprocess),
    reports its PID, then idles until terminated.
    """
    import subprocess
    import sys
    import time

    grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    pid_queue.put(grandchild.pid)
    time.sleep(30)


def _wait_until_pid_gone(pid: int, timeout: float = 15.0) -> bool:
    import time

    import psutil

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            proc = psutil.Process(pid)
            if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            return True
        time.sleep(0.05)
    return False


def test_dashboard_manager_shutdown_terminates_process_tree():
    """Regression for the Windows viewer-shutdown bug: shutdown() must terminate the viewer
    process *and* its descendants (e.g. WebView2 subprocesses), not just the viewer itself.
    """
    import multiprocessing

    import psutil

    from serena.agent import DashboardManager

    manager = DashboardManager(
        port=12345,
        host_listen_address="127.0.0.1",
        open_dashboard_on_launch=False,
        mode_str="browser",
    )

    pid_queue: "multiprocessing.Queue" = multiprocessing.Queue()
    viewer = multiprocessing.Process(target=_viewer_process_spawning_grandchild, args=(pid_queue,))
    viewer.start()
    try:
        grandchild_pid = pid_queue.get(timeout=15)
    except Exception:
        viewer.kill()
        raise
    viewer_pid = viewer.pid

    assert psutil.pid_exists(viewer_pid)
    assert psutil.pid_exists(grandchild_pid)

    manager._dashboard_viewer_process = viewer
    manager.shutdown()

    assert manager._dashboard_viewer_process is None
    assert _wait_until_pid_gone(viewer_pid), "viewer process still running after shutdown"
    assert _wait_until_pid_gone(grandchild_pid), "viewer descendant still running after shutdown"
