"""
Lean 4 language server implementation following the Pyright pattern.
Simple, reliable, and maintainable.
"""

import logging
import os
import pathlib
import subprocess
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class Lean4LanguageServer(SolidLanguageServer):
    """
    Lean 4 language server implementation.

    Follows the Pyright pattern - assumes Lean is installed via elan,
    uses direct server invocation, minimal state management.
    """

    def __init__(
        self,
        config: LanguageServerConfig,
        logger: LanguageServerLogger,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
    ):
        """
        Creates a Lean4LanguageServer instance.
        This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        # Verify Lean is available
        self._verify_lean_installation(logger)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd="lean --server", cwd=repository_root_path),
            "lean4",
            solidlsp_settings,
        )

        # Minimal state - just track if server is ready
        self.server_ready = threading.Event()

    @staticmethod
    def _verify_lean_installation(logger: LanguageServerLogger) -> None:
        """Verify that Lean 4 is installed and available."""
        try:
            result = subprocess.run(["lean", "--version"], capture_output=True, text=True, check=False, timeout=5)
            if result.returncode == 0:
                logger.log(f"Lean version: {result.stdout.strip()}", logging.INFO)
            else:
                raise RuntimeError(f"Lean returned error: {result.stderr}")
        except FileNotFoundError:
            raise RuntimeError(
                "Lean 4 is not installed. Please install Lean 4 via elan:\n"
                "curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Lean version check timed out")

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        """Ignore Lean build and dependency directories."""
        return super().is_ignored_dirname(dirname) or dirname in [
            "build",
            ".lake",
            "lake-packages",
        ]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns minimal initialize params for Lean 4 Language Server.
        Following the Pyright pattern - let the server use its defaults.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        return {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True},
                }
            },
            "trace": "off",
        }

    def _start_server(self):
        """
        Start the Lean 4 language server.
        Minimal setup following the Pyright pattern.
        """

        def window_log_message(msg):
            """Log window messages from the server."""
            if isinstance(msg, dict):
                message = msg.get("message", str(msg))
                level = msg.get("type", 3)  # Default to INFO
                if level == 1:  # ERROR
                    self.logger.log(f"Lean LSP Error: {message}", logging.ERROR)
                elif level == 2:  # WARNING
                    self.logger.log(f"Lean LSP Warning: {message}", logging.WARNING)
                else:
                    self.logger.log(f"Lean LSP: {message}", logging.INFO)

        # Register minimal handlers - only what's necessary
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", lambda params: None)
        self.server.on_notification("textDocument/publishDiagnostics", lambda params: None)

        # Start the server process
        self.logger.log("Starting Lean 4 language server", logging.INFO)
        self.server.start()

        # Send initialization
        initialize_params = self._get_initialize_params(self.repository_root_path)
        self.logger.log("Sending initialize request to Lean 4 server", logging.INFO)

        init_response = self.server.send.initialize(initialize_params)
        self.logger.log("Received initialization response from Lean 4 server", logging.INFO)

        # Basic capability verification
        capabilities = init_response.get("capabilities", {})
        if not capabilities:
            self.logger.log("Warning: Server returned no capabilities", logging.WARNING)

        # Complete initialization
        self.server.notify.initialized({})
        self.completions_available.set()
        self.server_ready.set()

        self.logger.log("Lean 4 language server ready", logging.INFO)
