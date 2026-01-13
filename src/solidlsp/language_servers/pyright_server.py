"""
Provides Python specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Python.
"""

import logging
import os
import pathlib
import re
import threading
from typing import cast

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class PyrightServer(SolidLanguageServer):
    """
    Provides Python specific instantiation of the LanguageServer class using Pyright.
    Contains various configurations and settings specific to Python.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a PyrightServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        custom_command = solidlsp_settings.get_ls_specific_settings(self.get_language_enum_instance()).get("command", None)
        if custom_command:
            cmd = custom_command
        else:
            cmd = "python -m pyright.langserver --stdio"
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
            "python",
            solidlsp_settings,
        )

        # Event to signal when initial workspace analysis is complete
        self.analysis_complete = threading.Event()
        self.found_source_files = False

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["venv", "__pycache__"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Pyright Language Server.
        """
        # Create basic initialization parameters
        initialize_params = {  # type: ignore
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": pathlib.Path(repository_absolute_path).as_uri(),
            "initializationOptions": {
                "exclude": [
                    "**/__pycache__",
                    "**/.venv",
                    "**/.env",
                    "**/build",
                    "**/dist",
                    "**/.pixi",
                ],
                "reportMissingImports": "error",
            },
            "capabilities": {
                "workspace": {
                    "workspaceEdit": {"documentChanges": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "executeCommand": {"dynamicRegistration": True},
                },
                "textDocument": {
                    "synchronization": {"dynamicRegistration": True, "willSave": True, "willSaveWaitUntil": True, "didSave": True},
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True},
                        },
                    },
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "publishDiagnostics": {"relatedInformation": True},
                },
            },
            "workspaceFolders": [
                {"uri": pathlib.Path(repository_absolute_path).as_uri(), "name": os.path.basename(repository_absolute_path)}
            ],
        }

        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """
        Starts the Pyright Language Server and waits for initial workspace analysis to complete.

        This prevents zombie processes by ensuring Pyright has finished its initial background
        tasks before we consider the server ready.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and workspace analysis is complete
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown cleanly
        ```
        """

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            """
            Monitor Pyright's log messages to detect when initial analysis is complete.
            Pyright logs "Found X source files" when it finishes scanning the workspace.
            """
            message_text = msg.get("message", "")
            log.info(f"LSP: window/logMessage: {message_text}")

            # Look for "Found X source files" which indicates workspace scanning is complete
            # Unfortunately, pyright is unreliable and there seems to be no better way
            if re.search(r"Found \d+ source files?", message_text):
                log.info("Pyright workspace scanning complete")
                self.found_source_files = True
                self.analysis_complete.set()
                self.completions_available.set()

        def check_experimental_status(params: dict) -> None:
            """
            Also listen for experimental/serverStatus as a backup signal
            """
            if params.get("quiescent") == True:
                log.info("Received experimental/serverStatus with quiescent=true")
                if not self.found_source_files:
                    self.analysis_complete.set()
                    self.completions_available.set()

        # Set up notification handlers
        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        log.info("Starting pyright-langserver server process")
        self.server.start()

        # Send proper initialization parameters
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to pyright server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.info(f"Received initialize response from pyright server: {init_response}")

        # Verify that the server supports our required features
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        # Complete the initialization handshake
        self.server.notify.initialized({})

        # Wait for Pyright to complete its initial workspace analysis
        # This prevents zombie processes by ensuring background tasks finish
        log.info("Waiting for Pyright to complete initial workspace analysis...")
        if self.analysis_complete.wait(timeout=5.0):
            log.info("Pyright initial analysis complete, server ready")
        else:
            log.warning("Timeout waiting for Pyright analysis completion, proceeding anyway")
            # Fallback: assume analysis is complete after timeout
            self.analysis_complete.set()
            self.completions_available.set()
