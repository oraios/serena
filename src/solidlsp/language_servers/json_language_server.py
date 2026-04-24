"""
Provides JSON specific instantiation of the LanguageServer class using vscode-json-languageserver.
Contains various configurations and settings specific to JSON files.
"""

import logging
import os
import pathlib
import shutil
from typing import Any

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class JsonLanguageServer(SolidLanguageServer):
    """
    Provides JSON specific instantiation of the LanguageServer class using vscode-json-languageserver.
    Contains various configurations and settings specific to JSON files.

    Note: Cross-file references are not supported for JSON (the language server only provides
    document symbols and hover). JSON is useful for getting a structured overview of JSON files
    and navigating their contents.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a JsonLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "json",
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for JSON Language Server and return the path to the executable.
            """
            is_node_installed = shutil.which("node") is not None
            assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            is_npm_installed = shutil.which("npm") is not None
            assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

            json_language_server_version = self._custom_settings.get("json_language_server_version", "1.3.4")
            npm_registry = self._custom_settings.get("npm_registry")

            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="vscode-json-languageserver",
                        description="vscode-json-languageserver package (Microsoft)",
                        command=build_npm_install_command("vscode-json-languageserver", json_language_server_version, npm_registry),
                        platform_id="any",
                    ),
                ]
            )

            json_ls_dir = os.path.join(self._ls_resources_dir, "json-lsp")
            json_executable_path = os.path.join(json_ls_dir, "node_modules", ".bin", "vscode-json-languageserver")

            if os.name == "nt":
                json_executable_path += ".cmd"

            if not os.path.exists(json_executable_path):
                log.info(f"JSON Language Server executable not found at {json_executable_path}. Installing...")
                deps.install(json_ls_dir)
                log.info("JSON language server dependencies installed successfully")

            if not os.path.exists(json_executable_path):
                raise FileNotFoundError(
                    f"vscode-json-languageserver executable not found at {json_executable_path}, something went wrong with the installation."
                )

            return json_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the JSON Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """
        Starts the JSON Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        def register_capability_handler(params: Any) -> None:
            return

        def do_nothing(params: Any) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting JSON server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from JSON server: {init_response}")

        if "documentSymbolProvider" in init_response.get("capabilities", {}):
            log.info("JSON server supports document symbols")
        else:
            log.warning("Warning: JSON server does not report document symbol support")

        self.server.notify.initialized({})

        log.info("JSON server initialization complete")
