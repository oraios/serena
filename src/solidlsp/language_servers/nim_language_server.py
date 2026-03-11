"""
Provides Nim specific instantiation of the LanguageServer class using nimlangserver
(https://github.com/nim-lang/langserver).
"""

import logging
import os
import pathlib
import platform
import shutil

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class NimLanguageServer(SolidLanguageServer):
    """
    Provides Nim specific instantiation of the LanguageServer class using nimlangserver.
    """

    @staticmethod
    def _check_nimlangserver_installed() -> bool:
        """Check if nimlangserver is installed in the system."""
        return shutil.which("nimlangserver") is not None

    @staticmethod
    def _setup_runtime_dependency() -> str:
        """
        Verify that nimlangserver is available and return its path.
        Raises RuntimeError with helpful message if missing.
        """
        if platform.system() == "Windows":
            raise RuntimeError(
                "Nim language server support on Windows is experimental. "
                "Please install nimlangserver via nimble and add it to your PATH."
            )

        nimlangserver_path = shutil.which("nimlangserver")
        if not nimlangserver_path:
            raise RuntimeError(
                "nimlangserver (Nim Language Server) is not installed.\n"
                "Please install it using one of the following methods:\n"
                "  - Using nimble: nimble install nimlangserver\n"
                "  - From the GitHub releases: https://github.com/nim-lang/langserver/releases\n"
                "After installation, make sure 'nimlangserver' is in your PATH.\n"
                "Nim itself can be installed from https://nim-lang.org/install.html"
            )

        return nimlangserver_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        nimlangserver_path = self._setup_runtime_dependency()

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=nimlangserver_path, cwd=repository_root_path),
            "nim",
            solidlsp_settings,
        )
        self.request_id = 0

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Nim Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                        },
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "configuration": True,
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
            "initializationOptions": {},
        }
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """Start nimlangserver process."""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting nimlangserver process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # nimlangserver is ready after initialization
