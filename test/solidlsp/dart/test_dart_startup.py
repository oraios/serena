"""Regression test for Dart analyzer-status notification handling."""

import logging
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from solidlsp.language_servers.dart_language_server import DartLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.ls_process import LanguageServerInterface
from solidlsp.settings import SolidLSPSettings

pytestmark = pytest.mark.dart


class _FakeLanguageServerInterface(LanguageServerInterface):
    def __init__(self) -> None:
        super().__init__(LanguageServerId.DART, lambda _line: logging.INFO)
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def _start(self) -> None:
        self._running = True

    def _stop(self, timeout: float) -> None:
        self._running = False

    def _send_payload(self, payload: dict[str, Any]) -> None:
        if "id" not in payload:
            return
        result: Any = {"capabilities": {}} if payload.get("method") == "initialize" else None
        self._receive_payload({"jsonrpc": "2.0", "id": payload["id"], "result": result})

    def receive_notification(self, method: str, params: Any) -> None:
        self._receive_payload({"jsonrpc": "2.0", "method": method, "params": params})


def test_analyzer_status_notification_is_handled_after_startup(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "global"),
        project_data_path=str(tmp_path / "project"),
        ls_specific_settings={LanguageServerId.DART: {}},
    )
    server_interface = _FakeLanguageServerInterface()

    with (
        patch.object(
            DartLanguageServer,
            "_setup_runtime_dependencies",
            return_value=str(tmp_path / "dart-sdk"),
        ),
        patch.object(
            DartLanguageServer,
            "_create_language_server_interface",
            return_value=server_interface,
        ),
        # No readiness signal is ever sent here, so keep the fallback wait short.
        patch.object(DartLanguageServer, "_TIMEOUT_FOR_INITIAL_ANALYSIS", 0.05),
    ):
        server = DartLanguageServer(
            LanguageServerConfig(ls_id=LanguageServerId.DART),
            str(tmp_path),
            settings,
        )
        server.start()

    with caplog.at_level(logging.WARNING):
        server_interface.receive_notification("$/analyzerStatus", {"isAnalyzing": True})

    assert "Unhandled method '$/analyzerStatus'" not in caplog.messages


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("experimental/serverStatus", {"quiescent": True}),
        ("$/analyzerStatus", {"isAnalyzing": False}),
    ],
)
def test_start_waits_for_analysis_readiness_signal(
    tmp_path: Path,
    method: str,
    params: dict[str, Any],
) -> None:
    """`start()` must block until the Dart analysis server reports it has finished its
    initial workspace scan, instead of returning as soon as `initialized` is sent.
    """
    settings = SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "global"),
        project_data_path=str(tmp_path / "project"),
        ls_specific_settings={LanguageServerId.DART: {}},
    )
    server_interface = _FakeLanguageServerInterface()

    with (
        patch.object(
            DartLanguageServer,
            "_setup_runtime_dependencies",
            return_value=str(tmp_path / "dart-sdk"),
        ),
        patch.object(
            DartLanguageServer,
            "_create_language_server_interface",
            return_value=server_interface,
        ),
        patch.object(DartLanguageServer, "_TIMEOUT_FOR_INITIAL_ANALYSIS", 2.0, create=True),
    ):
        server = DartLanguageServer(
            LanguageServerConfig(ls_id=LanguageServerId.DART),
            str(tmp_path),
            settings,
        )

        start_thread = threading.Thread(target=server.start)
        start_thread.start()
        try:
            # No readiness signal has been sent yet: start() must still be blocked.
            start_thread.join(timeout=0.3)
            assert start_thread.is_alive(), "start() returned before any readiness signal was received"

            server_interface.receive_notification(method, params)

            start_thread.join(timeout=2.0)
            assert not start_thread.is_alive(), f"start() did not resume after {method} {params}"
        finally:
            if start_thread.is_alive():
                server_interface.receive_notification("experimental/serverStatus", {"quiescent": True})
                start_thread.join(timeout=2.0)


def test_start_proceeds_after_readiness_timeout_if_no_signal_arrives(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If neither readiness notification ever arrives, start() must still return once
    `_TIMEOUT_FOR_INITIAL_ANALYSIS` elapses, rather than blocking forever.
    """
    settings = SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "global"),
        project_data_path=str(tmp_path / "project"),
        ls_specific_settings={LanguageServerId.DART: {}},
    )
    server_interface = _FakeLanguageServerInterface()

    with (
        patch.object(
            DartLanguageServer,
            "_setup_runtime_dependencies",
            return_value=str(tmp_path / "dart-sdk"),
        ),
        patch.object(
            DartLanguageServer,
            "_create_language_server_interface",
            return_value=server_interface,
        ),
        patch.object(DartLanguageServer, "_TIMEOUT_FOR_INITIAL_ANALYSIS", 0.2, create=True),
    ):
        server = DartLanguageServer(
            LanguageServerConfig(ls_id=LanguageServerId.DART),
            str(tmp_path),
            settings,
        )

        start_thread = threading.Thread(target=server.start)
        with caplog.at_level(logging.WARNING):
            start_thread.start()
            start_thread.join(timeout=2.0)

        assert not start_thread.is_alive(), "start() never returned despite the readiness timeout elapsing"
        assert any("Timeout waiting for dart-language-server analysis completion" in m for m in caplog.messages)
        assert server.analysis_complete.is_set()
