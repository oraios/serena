"""Regression test for Dart analyzer-status notification handling."""

import logging
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
