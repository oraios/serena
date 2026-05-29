from collections.abc import Callable
from types import SimpleNamespace

import pytest

from serena.analytics import ToolUsageStats
from serena.dashboard import SerenaDashboardAPI
from solidlsp.ls_config import Language


class _DummyMemoryLogHandler:
    def get_log_messages(self, from_idx: int = 0):  # pragma: no cover - simple stub
        return SimpleNamespace(messages=[], max_idx=-1)

    def clear_log_messages(self) -> None:  # pragma: no cover - simple stub
        pass


class _DummyContext:
    name = "test-context"
    description = "test context description"
    _yaml_path = "/tmp/test-context.yaml"


class _DummyMode:
    name = "test-mode"
    description = "test mode description"
    _yaml_path = "/tmp/test-mode.yaml"


class _DummyLanguageBackend:
    def is_jetbrains(self) -> bool:
        return False


class _DummyAgent:
    version = "test-version"

    def __init__(self, project: SimpleNamespace | None = None) -> None:
        self._project = project
        self._all_tools: dict = {}
        self.serena_config = SimpleNamespace(projects=[])

    def register_config_changed_callback(self, callback: Callable[[], None]) -> None:
        pass

    def execute_task(self, func, *, logged: bool | None = None, name: str | None = None):
        del logged, name
        return func()

    def get_active_project(self):
        return self._project

    def get_current_tasks(self):
        return []

    def get_last_executed_task(self):
        return None

    def get_context(self):
        return _DummyContext()

    def get_active_modes(self):
        return []

    def get_active_tool_names(self):
        return []

    def tool_is_active(self, _name: str) -> bool:
        return False

    def get_language_backend(self):
        return _DummyLanguageBackend()


def _make_dashboard(project_languages: list[Language] | None) -> SerenaDashboardAPI:
    project = None
    if project_languages is not None:
        project = SimpleNamespace(project_config=SimpleNamespace(languages=project_languages))
    agent = _DummyAgent(project)
    return SerenaDashboardAPI(memory_log_handler=_DummyMemoryLogHandler(), tool_names=[], agent=agent, tool_usage_stats=None)


@pytest.fixture
def make_dashboard_with_stats():
    """Returns a callable (stats) -> (dashboard, client) where client is a Flask test client."""

    def _factory(stats: ToolUsageStats | None = None):
        agent = _DummyAgent()
        stats = stats if stats is not None else ToolUsageStats()
        dashboard = SerenaDashboardAPI(
            memory_log_handler=_DummyMemoryLogHandler(),
            tool_names=[],
            agent=agent,
            tool_usage_stats=stats,
        )
        return dashboard, dashboard._app.test_client()

    return _factory


def test_available_languages_include_experimental_when_no_active_project():
    dashboard = _make_dashboard(project_languages=None)
    response = dashboard._get_available_languages()
    expected = sorted(lang.value for lang in Language.iter_all(include_experimental=True))
    assert response.languages == expected


def test_available_languages_exclude_project_languages():
    dashboard = _make_dashboard(project_languages=[Language.PYTHON, Language.MARKDOWN])
    response = dashboard._get_available_languages()
    available = set(response.languages)
    assert Language.PYTHON.value not in available
    assert Language.MARKDOWN.value not in available
    # ensure experimental languages remain available for selection
    assert Language.ANSIBLE.value in available


# ---------------------------------------------------------------------------
# Task 6 — /get_tool_call_timeline
# ---------------------------------------------------------------------------


def test_get_tool_call_timeline_returns_records_with_cursor(make_dashboard_with_stats):
    dashboard, client = make_dashboard_with_stats()
    stats = dashboard._tool_usage_stats
    for i in range(5):
        stats.record_call(
            tool_name="t",
            input_str="",
            output_str="",
            duration_ms=1.0,
            success=True,
            error_message=None,
            now=1000.0 + i,
        )
    r = client.get("/get_tool_call_timeline")
    assert r.status_code == 200
    body = r.get_json()
    assert body["max_seq"] == 5
    assert len(body["records"]) == 5

    r = client.get("/get_tool_call_timeline?since_seq=3")
    body = r.get_json()
    assert [rec["seq"] for rec in body["records"]] == [4, 5]

    stats.record_call(
        tool_name="other",
        input_str="",
        output_str="",
        duration_ms=1.0,
        success=True,
        error_message=None,
        now=2000.0,
    )
    r = client.get("/get_tool_call_timeline?tool=other")
    body = r.get_json()
    assert all(rec["tool"] == "other" for rec in body["records"])

    r = client.get("/get_tool_call_timeline?limit=99999")
    assert r.status_code == 200  # capped server-side, no error

    r = client.get("/get_tool_call_timeline?since_seq=-1")
    assert r.status_code == 400  # 400 on negative cursor


def test_get_tool_call_timeline_empty_when_no_stats():
    """When tool_usage_stats is None, returns empty payload."""
    dashboard = SerenaDashboardAPI(
        memory_log_handler=_DummyMemoryLogHandler(),
        tool_names=[],
        agent=_DummyAgent(),
        tool_usage_stats=None,
    )
    client = dashboard._app.test_client()
    r = client.get("/get_tool_call_timeline")
    assert r.status_code == 200
    assert r.get_json() == {"records": [], "max_seq": 0}


# ---------------------------------------------------------------------------
# Task 7 — tool_stats_totals
# ---------------------------------------------------------------------------


def test_config_overview_includes_tool_stats_totals(make_dashboard_with_stats):
    dashboard, _client = make_dashboard_with_stats()
    stats = dashboard._tool_usage_stats
    stats.record_call(
        tool_name="t",
        input_str="abc",
        output_str="defg",
        duration_ms=10.0,
        success=True,
        error_message=None,
        now=1000.0,
    )
    stats.record_call(
        tool_name="t",
        input_str="x",
        output_str="y",
        duration_ms=20.0,
        success=False,
        error_message="Err: nope",
        now=1001.0,
    )
    response = dashboard._get_config_overview()
    totals = response.tool_stats_totals
    assert totals["num_calls"] == 2
    assert totals["num_errors"] == 1
    assert totals["total_duration_ms"] == 30.0
    assert totals["total_tokens"] >= 0


# ---------------------------------------------------------------------------
# Task 8 — QueuedExecution extension
# ---------------------------------------------------------------------------


def test_queued_execution_includes_timing_and_error_fields():
    from serena.dashboard import QueuedExecution
    from serena.task_executor import TaskExecutor

    task = TaskExecutor.Task(function=lambda: "ok", name="Task-7: read_file", logged=False)
    task.start()
    task.wait_until_done(timeout=2.0)
    info = TaskExecutor.TaskInfo.from_task(task, is_running=False)
    serialized = QueuedExecution.from_task_info(info).model_dump()

    assert serialized["display_name"] == "read_file"
    assert serialized["duration_ms"] is not None
    assert serialized["error_message"] is None
    assert serialized["started_at"] is not None
    assert serialized["finished_at"] is not None


def test_queued_executions_route_returns_extended_payload(make_dashboard_with_stats):
    from serena.task_executor import TaskExecutor

    dashboard, client = make_dashboard_with_stats()
    task = TaskExecutor.Task(function=lambda: "ok", name="Task-1: foo", logged=False)
    task.start()
    task.wait_until_done(timeout=2.0)
    info = TaskExecutor.TaskInfo.from_task(task, is_running=False)
    dashboard._agent.get_current_tasks = lambda: [info]

    r = client.get("/queued_task_executions")
    body = r.get_json()
    assert body["status"] == "success"
    assert body["queued_executions"][0]["display_name"] == "foo"
    assert body["queued_executions"][0]["duration_ms"] is not None
