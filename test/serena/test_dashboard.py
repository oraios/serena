from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from serena.config.context_mode import SerenaAgentContext
from serena.config.serena_config import AgentInterface
from serena.dashboard import SerenaDashboardAPI
from serena.language_backend import BuiltinLanguageBackend
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


@pytest.mark.parametrize("open_on_launch", [True, False, None])
@pytest.mark.parametrize("trusted", [True, False, None])
def test_config_overview_reports_project_trust(monkeypatch: pytest.MonkeyPatch, trusted: bool | None, open_on_launch: bool | None) -> None:
    # isolate background network work and provide the configuration used by the overview
    monkeypatch.setattr(SerenaDashboardAPI, "_fetch_news", lambda self: None)
    monkeypatch.setattr(SerenaDashboardAPI, "_determine_newer_serena_version", lambda self: None)
    agent = MagicMock()
    agent.version = "2.0.0"
    agent.get_context.return_value = SerenaAgentContext.load_default()
    agent.get_active_modes.return_value.get_modes.return_value = []
    agent.get_active_tool_names.return_value = []
    agent.serena_config.projects = []
    agent.serena_config.web_dashboard_open_on_launch = open_on_launch
    agent._all_tools = {}
    agent.is_tool_function_available.return_value = False
    agent.get_agent_interface.return_value = AgentInterface.TOOLS
    agent.get_language_backend.return_value = BuiltinLanguageBackend.LSP.get_instance()
    project = None
    if trusted is not None:
        project = MagicMock()
        project.project_name = "example"
        project.project_root = "/example"
        project.project_config.language_servers = []
        project.project_config.encoding = "utf-8"
        project.is_trusted.return_value = trusted
    agent.get_active_project.return_value = project
    dashboard = SerenaDashboardAPI(memory_log_handler=_DummyMemoryLogHandler(), tool_names=[], agent=agent)

    # expose a boolean for active projects and no trust status without a project
    response = dashboard._compute_config_overview().model_dump()
    assert response["web_dashboard_open_on_launch"] is open_on_launch
    assert response["active_project"]["is_trusted"] is trusted
    assert response["active_project"]["name"] == ("example" if project is not None else None)
