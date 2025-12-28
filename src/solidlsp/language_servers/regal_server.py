"""Regal Language Server implementation for Rego policy files."""

import logging
import os
import shutil
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class RegalLanguageServer(SolidLanguageServer):
    """
    Provides Rego specific instantiation of the LanguageServer class using Regal.

    Regal is the official linter and language server for Rego (Open Policy Agent's policy language).
    See: https://github.com/StyraInc/regal
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [".regal", ".opa"]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a RegalLanguageServer instance.

        This class is not meant to be instantiated directly. Use LanguageServer.create() instead.

        :param config: Language server configuration
        :param repository_root_path: Path to the repository root
        :param solidlsp_settings: Settings for solidlsp
        """
        # Regal should be installed system-wide (via CI or user installation)
        regal_executable_path = shutil.which("regal")
        if not regal_executable_path:
            raise RuntimeError(
                "Regal language server not found. Please install it from https://github.com/StyraInc/regal or via your package manager."
            )

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=f"{regal_executable_path} language-server", cwd=repository_root_path),
            "rego",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Regal Language Server.

        :param repository_absolute_path: Absolute path to the repository
        :return: LSP initialization parameters
        """
        root_uri = PathUtils.path_to_uri(repository_absolute_path)
        return {
            "processId": os.getpid(),
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},  # type: ignore[arg-type]
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},  # type: ignore[list-item]
                    "inlayHint": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [
                {
                    "name": os.path.basename(repository_absolute_path),
                    "uri": root_uri,
                }
            ],
        }

    def _start_server(self) -> None:
        """Start Regal language server process and wait for initialization."""

        def register_capability_handler(params) -> None:  # type: ignore[no-untyped-def]
            return

        def window_log_message(msg) -> None:  # type: ignore[no-untyped-def]
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params) -> None:  # type: ignore[no-untyped-def]
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Regal language server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info(
            "Sending initialize request from LSP client to LSP server and awaiting response",
        )
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "capabilities" in init_response
        assert "textDocumentSync" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()

        # Regal server is ready immediately after initialization
        self.server_ready.set()
        self.server_ready.wait()
