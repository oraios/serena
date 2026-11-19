# SPDX-License-Identifier: MIT
"""Regression coverage for C# file synchronization during project loading."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.settings import SolidLSPSettings

pytestmark = pytest.mark.csharp


def test_new_file_reload_waits_for_initial_load_and_its_own_completion(tmp_path: Path) -> None:
    # create a real adapter with a simulated Roslyn protocol connection
    (tmp_path / "Test.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk" />', encoding="utf-8")
    interface = Mock()
    interface.send.initialize.return_value = {
        "capabilities": {
            "textDocumentSync": 1,
            "definitionProvider": True,
            "referencesProvider": True,
            "documentSymbolProvider": True,
        }
    }
    with patch.object(CSharpLanguageServer, "_create_language_server_interface", return_value=interface):
        server = CSharpLanguageServer(
            LanguageServerConfig(ls_id=LanguageServerId.CSHARP),
            str(tmp_path),
            SolidLSPSettings(solidlsp_dir=str(tmp_path / "global"), project_data_path=str(tmp_path / "data")),
        )

    # simulate the startup indexing timeout while Roslyn continues loading
    indexing_complete = Mock()
    indexing_complete.wait.return_value = False
    with patch("solidlsp.language_servers.csharp_language_server.threading.Event", return_value=indexing_complete):
        server._start_server()
    log_handler = next(call.args[1] for call in interface.on_notification.call_args_list if call.args[0] == "window/logMessage")

    # observe the reload request at the protocol boundary
    reload_requested = Event()

    def on_notification(method: str, params: dict) -> None:
        if method == "project/open":
            reload_requested.set()

    interface.notify.send_notification.side_effect = on_notification
    (tmp_path / "New.cs").write_text("class New {}", encoding="utf-8")
    sync_started = Event()

    def synchronize() -> None:
        sync_started.set()
        server.notify_files_created(["New.cs"])

    def complete_load() -> None:
        log_handler({"type": 3, "message": "Completed (re)load of all projects"})

    with ThreadPoolExecutor(max_workers=1) as executor:
        synchronization = executor.submit(synchronize)
        try:
            assert sync_started.wait(5)
            assert not reload_requested.wait(0.1), "reload must wait for the initial project load"
            complete_load()
            assert reload_requested.wait(5), "initial load completion must allow the new-file reload"
            with pytest.raises(TimeoutError):
                synchronization.result(timeout=0.1)
            complete_load()
            synchronization.result(timeout=5)
        finally:
            # release the worker even when an assertion fails
            complete_load()
