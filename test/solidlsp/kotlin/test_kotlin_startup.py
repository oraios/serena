"""Regression tests for Kotlin LSP startup readiness handling."""

import logging
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from solidlsp.language_servers.kotlin_language_server import KotlinLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.settings import SolidLSPSettings

pytestmark = pytest.mark.kotlin

_REQUIRED_CAPABILITIES = {
    "textDocumentSync": 1,
    "hoverProvider": True,
    "completionProvider": {},
    "signatureHelpProvider": {},
    "definitionProvider": True,
    "referencesProvider": True,
    "documentSymbolProvider": True,
    "workspaceSymbolProvider": True,
    "semanticTokensProvider": {},
}


def _make_server(tmp_path: Path) -> tuple[KotlinLanguageServer, Mock, Mock]:
    settings = SolidLSPSettings(
        solidlsp_dir=str(tmp_path / "global"),
        project_data_path=str(tmp_path / "project"),
        ls_specific_settings={LanguageServerId.KOTLIN: {}},
    )
    server_interface = Mock()
    with patch.object(KotlinLanguageServer, "_create_language_server_interface", return_value=server_interface):
        server = KotlinLanguageServer(
            LanguageServerConfig(ls_id=LanguageServerId.KOTLIN),
            str(tmp_path),
            settings,
        )

    indexing_complete = Mock()
    indexing_complete.wait.return_value = True
    intellij_server_ready = Mock()
    intellij_server_ready.wait.return_value = True
    server_state = cast(Any, server)
    server_state._indexing_complete = indexing_complete
    server_state._intellij_server_ready = intellij_server_ready
    return server, indexing_complete, intellij_server_ready


def _configure_initialize(server: KotlinLanguageServer, server_name: str | None) -> dict[str, Any]:
    response: dict[str, Any] = {"capabilities": _REQUIRED_CAPABILITIES}
    if server_name is not None:
        response["serverInfo"] = {"name": server_name}
    language_server_interface = cast(Any, server.server)
    language_server_interface.send.initialize.return_value = response
    return response


def test_modern_server_registers_and_waits_for_explicit_ready_notification(tmp_path: Path) -> None:
    server, indexing_complete, intellij_server_ready = _make_server(tmp_path)
    _configure_initialize(server, "IntelliJ Language Server by JetBrains")
    events: list[str] = []
    notification_handlers: dict[str, Any] = {}
    language_server_interface = cast(Any, server.server)

    def on_notification(method: str, handler: Any) -> None:
        events.append(f"notification:{method}")
        notification_handlers[method] = handler

    language_server_interface.on_notification.side_effect = on_notification
    language_server_interface.start.side_effect = lambda: events.append("start")
    language_server_interface.send.initialize.side_effect = lambda _params: (
        events.append("initialize")
        or {"capabilities": _REQUIRED_CAPABILITIES, "serverInfo": {"name": "IntelliJ Language Server by JetBrains"}}
    )

    server._start_server()

    assert events.index("notification:intellij/ready-for-test") < events.index("start") < events.index("initialize")
    intellij_server_ready.clear.assert_called_once_with()
    intellij_server_ready.wait.assert_called_once_with(timeout=120.0)
    indexing_complete.wait.assert_not_called()

    notification_handlers["intellij/ready-for-test"](None)
    intellij_server_ready.set.assert_called_once_with()


def test_legacy_server_keeps_progress_event_wait(tmp_path: Path) -> None:
    server, indexing_complete, intellij_server_ready = _make_server(tmp_path)
    _configure_initialize(server, None)

    server._start_server()

    indexing_complete.wait.assert_called_once_with(timeout=120.0)
    intellij_server_ready.wait.assert_not_called()


def test_modern_ready_timeout_warns_and_continues(tmp_path: Path, caplog: Any) -> None:
    server, _indexing_complete, intellij_server_ready = _make_server(tmp_path)
    _configure_initialize(server, "IntelliJ Language Server by JetBrains")
    intellij_server_ready.wait.return_value = False

    with caplog.at_level(logging.WARNING):
        server._start_server()

    assert "Kotlin LSP did not signal indexing completion within 120s; proceeding anyway" in caplog.text


def test_storage_path_is_no_longer_hardcoded_none(tmp_path: Path) -> None:
    """A hardcoded None here means every instance shares the LSP's own default index
    location; two concurrent instances on the same project then contend for it and the
    second fails to index (oraios/serena#1966).
    """
    server, _indexing_complete, _intellij_server_ready = _make_server(tmp_path)

    storage_path = server._create_base_initialize_params()["initializationOptions"]["storagePath"]

    assert storage_path == str(tmp_path / "project" / "cache" / "kotlin")
