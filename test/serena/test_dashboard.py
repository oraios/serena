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


def test_dashboard_manager_shutdown_cleans_up_process_tree():
    from unittest.mock import MagicMock, patch

    from serena.agent import DashboardManager

    manager = DashboardManager(
        port=12345,
        host_listen_address="127.0.0.1",
        open_dashboard_on_launch=False,
        mode_str="browser",
    )
    mock_process = MagicMock()
    mock_process.is_alive.side_effect = [True, False]
    mock_process.pid = 99999
    manager._dashboard_viewer_process = mock_process

    mock_child = MagicMock()
    mock_psutil_proc = MagicMock()
    mock_psutil_proc.children.return_value = [mock_child]

    with (
        patch("serena.agent.psutil.Process", return_value=mock_psutil_proc) as mock_psutil,
        patch("serena.agent.psutil.wait_procs", return_value=([], [])) as mock_wait,
    ):
        manager.shutdown()

        mock_psutil.assert_called_once_with(99999)
        mock_psutil_proc.children.assert_called_once_with(recursive=True)
        mock_process.terminate.assert_called_once()
        mock_child.terminate.assert_called_once()
        mock_process.join.assert_called_once_with(timeout=2.0)
        mock_wait.assert_called_once_with([mock_child], timeout=1.0)
        assert manager._dashboard_viewer_process is None


def test_dashboard_manager_shutdown_falls_back_to_kill_on_timeout():
    from unittest.mock import MagicMock, patch

    from serena.agent import DashboardManager

    manager = DashboardManager(
        port=12345,
        host_listen_address="127.0.0.1",
        open_dashboard_on_launch=False,
        mode_str="browser",
    )
    mock_process = MagicMock()
    mock_process.is_alive.side_effect = [True, True]
    mock_process.pid = 99999
    manager._dashboard_viewer_process = mock_process

    mock_child = MagicMock()
    mock_psutil_proc = MagicMock()
    mock_psutil_proc.children.return_value = [mock_child]

    with (
        patch("serena.agent.psutil.Process", return_value=mock_psutil_proc),
        patch("serena.agent.psutil.wait_procs", return_value=([], [mock_child])),
    ):
        manager.shutdown()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        mock_child.kill.assert_called_once()
        assert manager._dashboard_viewer_process is None


def test_dashboard_manager_shutdown_when_process_already_exited():
    from unittest.mock import MagicMock

    from serena.agent import DashboardManager

    manager = DashboardManager(
        port=12345,
        host_listen_address="127.0.0.1",
        open_dashboard_on_launch=False,
        mode_str="browser",
    )
    mock_process = MagicMock()
    mock_process.is_alive.return_value = False
    manager._dashboard_viewer_process = mock_process

    manager.shutdown()

    mock_process.join.assert_called_once_with(timeout=0.5)
    assert manager._dashboard_viewer_process is None
