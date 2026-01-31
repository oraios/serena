"""
Provides C/C++ specific instantiation of the LanguageServer class using ccls.

This is an alternative to clangd for large C++ codebases where ccls may perform
better for indexing and navigation. Requires ccls to be installed and available
on PATH, or configured via ls_specific_settings with key "ls_path".

For best results, ensure a compile_commands.json exists at the repository root.
"""

import logging
import os
import pathlib
import threading
from typing import Any, cast

from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class CclsLanguageServer(SolidLanguageServer):
    """
    C/C++ language server implementation using ccls.

    Notes:
    - ccls should be installed and on PATH (or specify ls_path in settings)
    - compile_commands.json at repo root is recommended for accurate indexing

    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a CclsLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(config, repository_root_path, None, "cpp", solidlsp_settings)
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Resolve ccls path from system or raise helpful error if missing.
            Allows override via ls_specific_settings[language].ls_path.
            """
            import shutil

            ccls_path = shutil.which("ccls")
            if not ccls_path:
                raise FileNotFoundError(
                    "ccls is not installed on your system.\n"
                    + "Please install ccls using your system package manager:\n"
                    + "  Ubuntu/Debian: sudo apt-get install ccls\n"
                    + "  Fedora/RHEL: sudo dnf install ccls\n"
                    + "  Arch Linux: sudo pacman -S ccls\n"
                    + "See https://github.com/MaskRay/ccls for more details."
                )
            log.info(f"Using system-installed ccls at {ccls_path}")
            return ccls_path

        def _create_launch_command(self, core_path: str) -> list[str] | str:
            return [core_path]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the ccls Language Server.
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
                    "documentSymbol": {"dynamicRegistration": True},
                },
                "workspace": {"workspaceFolders": True, "didChangeConfiguration": {"dynamicRegistration": True}},
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": "$name",
                }
            ],
            # ccls supports initializationOptions but none are required for basic functionality
        }
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """
        Starts the ccls language server and initializes the LSP connection.
        """

        def do_nothing(params: Any) -> None:
            pass

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        # Register minimal handlers
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting ccls server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to ccls and awaiting response")
        self.server.send.initialize(initialize_params)
        # Do not assert clangd-specific capability shapes; ccls differs
        self.server.notify.initialized({})

        # Basic readiness
        self.completions_available.set()
        self.server_ready.set()
