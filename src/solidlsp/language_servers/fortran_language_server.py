"""
Fortran Language Server implementation using fortls.
"""

import logging
import os
import pathlib
import shutil
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class FortranLanguageServer(SolidLanguageServer):
    """Fortran Language Server implementation using fortls."""

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 3.0  # fortls needs time for workspace indexing

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Fortran projects, ignore common build directories
        return super().is_ignored_dirname(dirname) or dirname in [
            "build",
            "Build",
            "BUILD",
            "bin",
            "lib",
            "mod",  # Module files directory
            "obj",  # Object files directory
            ".cmake",
            "CMakeFiles",
        ]

    @staticmethod
    def _check_fortls_installation():
        """Check if fortls is available."""
        fortls_path = shutil.which("fortls")
        if fortls_path is None:
            raise RuntimeError(
                "fortls is not installed or not in PATH.\n"
                "Install it with: pip install fortls"
            )
        return fortls_path

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        # Check fortls installation
        fortls_path = self._check_fortls_installation()

        # Command to start fortls language server
        # fortls uses stdio for LSP communication by default
        fortls_cmd = f"{fortls_path}"

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=fortls_cmd, cwd=repository_root_path),
            "fortran",  # Language ID for LSP
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Initialize params for Fortran Language Server."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
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
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
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
        return initialize_params

    def _start_server(self):
        """Start Fortran Language Server process."""

        def window_log_message(msg):
            self.logger.log(f"Fortran LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(params):
            return

        def register_capability_handler(params):
            return

        # Register LSP message handlers
        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting Fortran Language Server (fortls) process", logging.INFO)
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        self.logger.log(
            "Sending initialize request to Fortran Language Server",
            logging.INFO,
        )

        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        capabilities = init_response.get("capabilities", {})
        assert "textDocumentSync" in capabilities
        if "completionProvider" in capabilities:
            self.logger.log("Fortran LSP completion provider available", logging.INFO)
        if "definitionProvider" in capabilities:
            self.logger.log("Fortran LSP definition provider available", logging.INFO)
        if "referencesProvider" in capabilities:
            self.logger.log("Fortran LSP references provider available", logging.INFO)
        if "documentSymbolProvider" in capabilities:
            self.logger.log("Fortran LSP document symbol provider available", logging.INFO)

        self.server.notify.initialized({})
        self.completions_available.set()

        # Fortran Language Server is ready after initialization
        self.server_ready.set()
        self.logger.log("Fortran Language Server initialization complete", logging.INFO)

