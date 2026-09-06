"""Automatic type acquisition must be disabled on the semantic TypeScript worker."""

import copy
import os
import threading
from pathlib import Path
from unittest.mock import Mock

import psutil
import pytest

from solidlsp.language_servers.vts_language_server import VtsLanguageServer
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId
from solidlsp.settings import SolidLSPSettings
from test.conftest import get_repo_path, start_ls_context


@pytest.mark.typescript
@pytest.mark.parametrize("backend", [LanguageServerId.TYPESCRIPT, LanguageServerId.TYPESCRIPT_VTS])
def test_default_disables_type_acquisition_in_running_server(backend: LanguageServerId) -> None:
    parent = psutil.Process(os.getpid())
    existing_pids = {child.pid for child in parent.children(recursive=True)}

    # VTS uses the same fixture project, but has no default repository alias.
    with start_ls_context(backend, repo_path=str(get_repo_path(LanguageServerId.TYPESCRIPT))) as ls:
        symbols = ls.request_document_symbols("index.ts").get_all_symbols_and_roots()[0]
        assert any(symbol["name"] == "DemoClass" for symbol in symbols)

        semantic_workers = []
        typings_installers = []
        for child in parent.children(recursive=True):
            if child.pid in existing_pids:
                continue
            try:
                command = child.cmdline()
            except psutil.NoSuchProcess:
                continue
            filenames = {Path(arg).name for arg in command}
            if "typingsInstaller.js" in filenames:
                typings_installers.append(command)
            if "tsserver.js" in filenames and "partialSemantic" not in command and "--syntaxOnly" not in command:
                semantic_workers.append(command)

        # The syntax worker disables ATA independently, even on the broken baseline.
        assert semantic_workers, "No semantic tsserver was observed after a successful symbol request"
        assert all("--disableAutomaticTypingAcquisition" in command for command in semantic_workers), semantic_workers
        assert not typings_installers, typings_installers


@pytest.mark.parametrize(
    ("custom_settings", "expected"),
    [
        ({}, {"typescript": {"disableAutomaticTypeAcquisition": True}}),
        (
            {"initialization_options": {"typescript": {"tsdk": "workspace/typescript/lib"}, "vtsls": {"autoUseWorkspaceTsdk": True}}},
            {
                "typescript": {"tsdk": "workspace/typescript/lib", "disableAutomaticTypeAcquisition": True},
                "vtsls": {"autoUseWorkspaceTsdk": True},
            },
        ),
        (
            {"initialization_options": {"typescript": {"disableAutomaticTypeAcquisition": False}}},
            {"typescript": {"disableAutomaticTypeAcquisition": False}},
        ),
        (
            {"initializationOptions": {"typescript": {"tsdk": "workspace/typescript/lib"}}},
            {"typescript": {"tsdk": "workspace/typescript/lib", "disableAutomaticTypeAcquisition": True}},
        ),
    ],
)
def test_vts_sends_consistent_effective_configuration(tmp_path: Path, custom_settings: dict, expected: dict) -> None:
    original_settings = copy.deepcopy(custom_settings)

    # Use the real startup/configuration path with only the remote LSP transport replaced.
    server = object.__new__(VtsLanguageServer)
    server._custom_settings = SolidLSPSettings.CustomLSSettings(custom_settings)
    server.repository_root_path = str(tmp_path)
    server.config = LanguageServerConfig(ls_id=LanguageServerId.TYPESCRIPT_VTS)
    server.server_ready = threading.Event()
    server.server_ready.set()
    server.initialize_searcher_command_available = threading.Event()
    transport = Mock()
    transport.send.initialize.return_value = {"capabilities": {"textDocumentSync": 1, "completionProvider": {}}}
    handlers = {}
    transport.on_request.side_effect = handlers.__setitem__
    server.server = transport

    server._start_server()

    assert transport.send.initialize.call_args.args[0]["initializationOptions"] == expected
    configuration = handlers["workspace/configuration"]
    assert configuration({"items": [{"section": ""}, {}, {"section": "typescript"}, {"section": "missing"}]}) == [
        expected,
        expected,
        expected["typescript"],
        {},
    ]
    assert transport.notify.workspace_did_change_configuration.call_args.args[0] == {"settings": expected}
    assert custom_settings == original_settings
