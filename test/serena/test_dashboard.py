from collections.abc import Callable
from types import SimpleNamespace

import pytest

from serena.agent import AvailableTools, ProjectPromptProvisionStatus, SerenaAgent
from serena.config.context_mode import SerenaAgentContext
from serena.config.serena_config import LanguageBackend
from serena.dashboard import SerenaDashboardAPI
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import (
    FilenameMatcher,
    LanguageServerConfig,
    LanguageServerId,
    LanguageServerKey,
    RegisteredLanguageServerId,
    _reset_registered_language_servers_for_tests,
    register_ls,
)
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class DummyExternalLanguageServer(SolidLanguageServer):
    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=["dummy"], cwd=repository_root_path), "dummy", solidlsp_settings
        )

    def _create_base_initialize_params(self) -> dict:
        return {}

    def _start_server(self) -> None:
        self.server.start()


@pytest.fixture(autouse=True)
def isolated_registry():
    _reset_registered_language_servers_for_tests()
    yield
    _reset_registered_language_servers_for_tests()


def _register_external_language_server() -> RegisteredLanguageServerId:
    return register_ls("external-test", FilenameMatcher(".external"), DummyExternalLanguageServer)


class _DummyMemoryLogHandler:
    def get_log_messages(self, from_idx: int = 0):  # pragma: no cover - simple stub
        return SimpleNamespace(messages=[], max_idx=-1)

    def clear_log_messages(self) -> None:  # pragma: no cover - simple stub
        pass


class _DummyAgent:
    def __init__(self, project: SimpleNamespace | None) -> None:
        self._project = project
        self.added_languages: list[LanguageServerKey] = []
        self.removed_languages: list[LanguageServerKey] = []
        self.serena_config = SimpleNamespace(projects=[])
        self.version = "test"
        self._all_tools = {}
        self._context = SerenaAgentContext.from_name("desktop-app")

    def register_config_changed_callback(self, callback: Callable[[], None]) -> None:
        pass

    def execute_task(self, func, *, logged: bool | None = None, name: str | None = None):
        del logged, name
        return func()

    def get_active_project(self):
        return self._project

    def get_context(self):
        return self._context

    def get_active_modes(self):
        return SimpleNamespace(get_modes=lambda include_background_base_modes=False: [])

    def get_active_tool_names(self):
        return []

    def tool_is_active(self, tool_name: str) -> bool:
        return False

    def get_language_backend(self):
        return SimpleNamespace(is_jetbrains=lambda: False)

    def add_language_server(self, language: LanguageServerKey) -> None:
        self.added_languages.append(language)

    def remove_language_server(self, language: LanguageServerKey) -> None:
        self.removed_languages.append(language)


def _make_dashboard(project_languages: list[LanguageServerKey] | None) -> SerenaDashboardAPI:
    project = None
    if project_languages is not None:
        project = SimpleNamespace(
            project_name="test-project",
            project_root="/test/project",
            project_config=SimpleNamespace(language_servers=project_languages, encoding="utf-8"),
        )
    agent = _DummyAgent(project)
    dashboard = SerenaDashboardAPI.__new__(SerenaDashboardAPI)
    dashboard._agent = agent
    dashboard._memory_log_handler = _DummyMemoryLogHandler()
    dashboard._tool_names = []
    dashboard._tool_usage_stats = None
    dashboard._newer_serena_version = None
    return dashboard


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


def test_available_languages_include_registered_external_language_server():
    _register_external_language_server()

    response = _make_dashboard(project_languages=None)._get_available_languages()

    assert "external-test" in response.languages
    assert LanguageServerId.PYTHON.value in response.languages
    assert response.languages == sorted(response.languages)


def test_available_languages_exclude_configured_external_language_server():
    external_id = _register_external_language_server()

    response = _make_dashboard(project_languages=[external_id])._get_available_languages()

    assert "external-test" not in response.languages


def test_add_and_remove_registered_external_language_server():
    external_id = _register_external_language_server()
    dashboard = _make_dashboard(project_languages=[LanguageServerId.PYTHON])
    agent = dashboard._agent

    dashboard._add_language(SimpleNamespace(language="external-test"))
    dashboard._remove_language(SimpleNamespace(language="external-test"))

    assert agent.added_languages == [external_id]
    assert agent.removed_languages == [external_id]


def test_add_and_remove_builtin_language_server_remain_supported():
    dashboard = _make_dashboard(project_languages=[])
    agent = dashboard._agent

    dashboard._add_language(SimpleNamespace(language="python"))
    dashboard._remove_language(SimpleNamespace(language="python"))

    assert agent.added_languages == [LanguageServerId.PYTHON]
    assert agent.removed_languages == [LanguageServerId.PYTHON]


def test_add_and_remove_unknown_language_server_are_rejected():
    dashboard = _make_dashboard(project_languages=[])

    with pytest.raises(ValueError, match="Invalid language server identifier: missing-external"):
        dashboard._add_language(SimpleNamespace(language="missing-external"))
    with pytest.raises(ValueError, match="Invalid language server identifier: missing-external"):
        dashboard._remove_language(SimpleNamespace(language="missing-external"))


def test_config_overview_includes_builtin_and_registered_external_language_servers():
    external_id = _register_external_language_server()
    dashboard = _make_dashboard(project_languages=[LanguageServerId.PYTHON, external_id])

    overview = dashboard._compute_config_overview()

    assert overview.languages == ["python", "external-test"]
    assert overview.active_project["language"] == "python, external-test"


def test_project_activation_message_includes_builtin_and_registered_external_language_servers():
    external_id = _register_external_language_server()
    agent = SerenaAgent.__new__(SerenaAgent)
    agent._active_project = SimpleNamespace(
        is_newly_created=False,
        project_name="test-project",
        project_root="/test/project",
        project_config=SimpleNamespace(
            language_servers=[LanguageServerId.PYTHON, external_id],
            encoding="utf-8",
            initial_prompt="",
        ),
    )
    agent._language_backend = LanguageBackend.LSP
    agent._active_tools = AvailableTools([])
    agent._project_prompt_status = ProjectPromptProvisionStatus()
    agent._gui_log_viewer = None
    agent._dashboard_manager = None

    try:
        message = agent.get_project_activation_message("test-session")
    finally:
        agent._active_project = None

    assert "Active language servers: python, external-test." in message
