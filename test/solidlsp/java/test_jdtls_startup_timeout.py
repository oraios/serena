"""Unit tests for bounded Eclipse JDTLS startup waits."""

import threading
from typing import Any, cast

import pytest

from solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.settings import SolidLSPSettings


class _FakeProtocolServer:
    def __init__(self, stop_error: Exception | None = None) -> None:
        self.stop_calls: list[float] = []
        self.stop_error = stop_error

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_calls.append(timeout)
        if self.stop_error is not None:
            raise self.stop_error


def _bare_jdtls(
    custom_settings: dict | None = None,
    *,
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
    protocol_server = _FakeProtocolServer(stop_error)
    server.server = cast(Any, protocol_server)
    server.server_started = True
    return server, protocol_server


def test_startup_timeout_default_and_override() -> None:
    server, _ = _bare_jdtls()
    assert server._get_startup_timeout() == 600.0

    server, _ = _bare_jdtls({"startup_timeout": 12.5})
    assert server._get_startup_timeout() == 12.5


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

    server._wait_for_startup_signal(event, "service_ready")

    assert server._startup_phase == "service_ready_received"
    assert protocol_server.stop_calls == []
    assert server.server_started


def test_startup_timeout_reports_phase_and_last_status_then_stops_server() -> None:
    server, protocol_server = _bare_jdtls({"startup_timeout": 0.001})
    server._handle_language_status({"type": "ProjectStatus", "message": "Starting"})

    with pytest.raises(SolidLSPException) as exc_info:
        server._wait_for_startup_signal(threading.Event(), "service_ready")

    message = str(exc_info.value)
    assert "after 0.001 seconds" in message
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

    with pytest.raises(SolidLSPException, match="waiting for intellicode_command_registration"):
        server._wait_for_startup_signal(threading.Event(), "intellicode_command_registration")

    assert protocol_server.stop_calls == [5.0]
    assert not server.server_started
