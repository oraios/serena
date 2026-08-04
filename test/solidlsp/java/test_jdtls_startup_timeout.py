"""Unit tests for bounded Eclipse JDTLS startup waits."""

import threading
from types import SimpleNamespace
from typing import Any, cast

import pytest

from serena.task_executor import TaskExecutor
from serena.tools.tools_base import Tool, ToolMarkerDoesNotRequireActiveProject
from solidlsp.language_servers import eclipse_jdtls as eclipse_jdtls_module
from solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.settings import SolidLSPSettings


class _FakeProtocolServer:
    def __init__(self, stop_error: Exception | None = None) -> None:
        self.stop_calls: list[float] = []
        self.request_timeouts: list[float | None] = []
        self.stop_error = stop_error

    def set_request_timeout(self, timeout: float | None) -> None:
        self.request_timeouts.append(timeout)

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_calls.append(timeout)
        if self.stop_error is not None:
            raise self.stop_error


def _bare_jdtls(
    custom_settings: dict | None = None,
    *,
    request_timeout: float | None = None,
    stop_error: Exception | None = None,
) -> tuple[EclipseJDTLS, _FakeProtocolServer]:
    """Build only the state touched by the startup timeout helpers."""
    server = object.__new__(EclipseJDTLS)
    server._custom_settings = SolidLSPSettings.CustomLSSettings(custom_settings)
    server._service_ready_event = threading.Event()
    server._project_ready_event = threading.Event()
    server._intellicode_enable_command_available = threading.Event()
    server._startup_phase = "not_started"
    server._last_language_status = None
    server._effective_startup_timeout = None
    server._startup_deadline = None
    server._request_timeout = None
    protocol_server = _FakeProtocolServer(stop_error)
    server.server = cast(Any, protocol_server)
    server.server_started = True
    server.set_request_timeout(request_timeout)
    return server, protocol_server


def test_startup_timeout_default_and_override() -> None:
    server, _ = _bare_jdtls()
    assert server._get_startup_timeout() == 600.0

    server, _ = _bare_jdtls({"startup_timeout": 12.5})
    assert server._get_startup_timeout() == 12.5


def test_startup_timeout_is_capped_below_outer_tool_budget() -> None:
    # Serena derives this 595-second LS request timeout from a 600-second outer tool timeout.
    server, protocol_server = _bare_jdtls(request_timeout=595)

    assert protocol_server.request_timeouts == [595]
    assert server._get_startup_shutdown_timeout() == 5
    assert server._get_effective_startup_timeout() == 590


@pytest.mark.parametrize("configured_timeout", [0, -1, "invalid", float("inf"), float("nan")])
def test_startup_timeout_must_be_positive_and_finite(configured_timeout: object) -> None:
    server, _ = _bare_jdtls({"startup_timeout": configured_timeout})

    with pytest.raises(SolidLSPException, match="positive finite number"):
        server._get_startup_timeout()


def test_language_status_handler_tracks_latest_status_and_sets_events() -> None:
    server, _ = _bare_jdtls()

    server._handle_language_status({"type": "ProjectStatus", "message": "OK"})
    assert server._project_ready_event.is_set()
    assert not server._service_ready_event.is_set()
    assert server._describe_last_language_status() == "type='ProjectStatus', message='OK'"

    server._handle_language_status({"type": "ServiceReady", "message": "ServiceReady"})
    assert server._service_ready_event.is_set()
    assert server._describe_last_language_status() == "type='ServiceReady', message='ServiceReady'"


def test_received_startup_signal_does_not_stop_server() -> None:
    server, protocol_server = _bare_jdtls({"startup_timeout": 1})
    event = threading.Event()
    event.set()

    server._begin_startup_deadline()
    server._wait_for_startup_signal(event, "service_ready")

    assert server._startup_phase == "service_ready_received"
    assert protocol_server.stop_calls == []
    assert server.server_started


def test_startup_timeout_reports_phase_and_last_status_then_stops_server() -> None:
    server, protocol_server = _bare_jdtls({"startup_timeout": 0.001})
    server._handle_language_status({"type": "ProjectStatus", "message": "Starting"})

    server._begin_startup_deadline()
    with pytest.raises(SolidLSPException) as exc_info:
        server._wait_for_startup_signal(threading.Event(), "service_ready")

    message = str(exc_info.value)
    assert "after 0.001 seconds total" in message
    assert "waiting for service_ready" in message
    assert "phase=waiting_for_service_ready" in message
    assert "last_language_status=type='ProjectStatus', message='Starting'" in message
    assert protocol_server.stop_calls == [5.0]
    assert not server.server_started


def test_shutdown_error_does_not_hide_startup_timeout() -> None:
    server, protocol_server = _bare_jdtls(
        {"startup_timeout": 0.001},
        stop_error=RuntimeError("shutdown failed"),
    )

    server._begin_startup_deadline()
    with pytest.raises(SolidLSPException, match="waiting for intellicode_command_registration"):
        server._wait_for_startup_signal(threading.Event(), "intellicode_command_registration")

    assert protocol_server.stop_calls == [5.0]
    assert not server.server_started


class _AdvancingEvent:
    def __init__(self, clock: list[float], elapsed: float) -> None:
        self.clock = clock
        self.elapsed = elapsed
        self.wait_timeouts: list[float | None] = []

    def wait(self, timeout: float | None = None) -> bool:
        self.wait_timeouts.append(timeout)
        self.clock[0] += self.elapsed
        return timeout is None or self.elapsed <= timeout


def test_required_signals_share_one_total_startup_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [100.0]
    monkeypatch.setattr(eclipse_jdtls_module, "monotonic", lambda: clock[0])
    server, _ = _bare_jdtls({"startup_timeout": 10})
    first_signal = _AdvancingEvent(clock, elapsed=6)
    second_signal = _AdvancingEvent(clock, elapsed=1)

    server._begin_startup_deadline()
    server._wait_for_startup_signal(cast(Any, first_signal), "intellicode_command_registration")
    server._wait_for_startup_signal(cast(Any, second_signal), "service_ready")

    assert first_signal.wait_timeouts == [10]
    assert second_signal.wait_timeouts == [4]


def test_startup_requests_use_remaining_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [100.0]
    monkeypatch.setattr(eclipse_jdtls_module, "monotonic", lambda: clock[0])
    server, protocol_server = _bare_jdtls(request_timeout=595)

    server._begin_startup_deadline()
    clock[0] += 10
    server._set_startup_request_timeout("initialize_response")

    assert protocol_server.request_timeouts == [595, 580]


class _FakeAgent:
    def __init__(self, tool_timeout: float) -> None:
        self.serena_config = SimpleNamespace(tool_timeout=tool_timeout)
        self._task_executor = TaskExecutor("JDTLSStartupTimeoutRegression")

    def tool_is_active(self, tool_name: str) -> bool:
        return True

    def issue_task(self, task, name: str | None = None, logged: bool = True, timeout: float | None = None):
        return self._task_executor.issue_task(task, name=name, logged=logged, timeout=timeout)

    def record_tool_usage(self, apply_kwargs: dict, result: str, tool: Tool) -> None:
        pass

    def get_language_server_manager(self):
        return None


class _StartupWaitTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    def __init__(self, agent: _FakeAgent, server: EclipseJDTLS) -> None:
        super().__init__(cast(Any, agent))
        self.server = server

    def apply(self) -> str:
        """Wait for a deliberately absent JDTLS startup signal."""
        self.server._begin_startup_deadline()
        self.server._wait_for_startup_signal(threading.Event(), "service_ready")
        raise AssertionError("The startup wait should have timed out")


def test_detailed_startup_error_surfaces_before_generic_tool_timeout() -> None:
    server, protocol_server = _bare_jdtls({"startup_timeout": 10}, request_timeout=0.2)
    server.STARTUP_SHUTDOWN_TIMEOUT = 0.05
    tool = _StartupWaitTool(_FakeAgent(tool_timeout=0.6), server)

    result = tool.apply_ex(log_call=False)

    assert "SolidLSPException: JDTLS startup timed out after 0.15 seconds total" in result
    assert "phase=waiting_for_service_ready" in result
    assert "last_language_status=none received" in result
    assert "Tool execution timed out" not in result
    assert protocol_server.stop_calls == [0.05]
