"""
Python language server integration using Astral's ``ty``.

You can pass the following entries in ``ls_specific_settings["python_ty"]``:
    - ls_path: Override the executable used to start ``ty``.
    - ty_version: Override the pinned ``ty`` version used with ``uvx`` / ``uv x``
      (default: the bundled Serena version).
"""

import logging
import os
import pathlib
import shutil
from typing import cast

from typing_extensions import override

from solidlsp.ls import LanguageServerDependencyProvider, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

TY_VERSION = "0.0.25"


class TyLanguageServer(SolidLanguageServer):
    """
    Provides Python specific instantiation of the LanguageServer class using ``ty``.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a TyLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            str(config.code_language),
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProvider):
        def create_launch_command(self) -> list[str]:
            # respecting an explicit override
            ls_path = self._custom_settings.get("ls_path")
            if ls_path is not None:
                return [ls_path, "server"]

            ty_version = self._custom_settings.get("ty_version", TY_VERSION)

            # preferring uvx for on-demand execution
            uvx_path = os.environ.get("UVX") or shutil.which("uvx")
            if uvx_path is not None:
                return [uvx_path, "--from", f"ty=={ty_version}", "ty", "server"]

            # falling back to uv's uvx-compatible subcommand when only `uv` is available
            uv_path = shutil.which("uv")
            if uv_path is not None:
                return [uv_path, "x", "--from", f"ty=={ty_version}", "ty", "server"]

            raise RuntimeError("Could not find 'uvx' or 'uv' in PATH.\nInstall uv or provide ls_specific_settings.python_ty.ls_path.")

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["venv", "__pycache__"]

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        return "python"

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Ty language server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "clientInfo": {"name": "Serena", "version": "0.1.0"},
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "workspace": {
                    "workspaceEdit": {"documentChanges": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                        "didSave": True,
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "implementation": {"dynamicRegistration": True, "linkSupport": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
            },
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """
        Starts the Ty language server.
        """

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg.get("message", ""))

        # setting up lightweight handlers
        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        # starting and initializing the server
        log.info("Starting ty language server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to ty server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.info("Received initialize response from ty server: %s", init_response)

        capabilities = init_response["capabilities"]
        assert "textDocumentSync" in capabilities
        assert "definitionProvider" in capabilities
        assert "referencesProvider" in capabilities
        assert "documentSymbolProvider" in capabilities

        # completing the initialization handshake
        self.server.notify.initialized({})
