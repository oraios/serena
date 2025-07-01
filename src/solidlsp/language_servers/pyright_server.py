"""
Provides Python specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Python.
"""

import logging
import os
import pathlib
import re
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


class PyrightServer(SolidLanguageServer):
    """
    Provides Python specific instantiation of the LanguageServer class using Pyright.
    Contains various configurations and settings specific to Python.
    """

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        """
        Creates a PyrightServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            logger,
            repository_root_path,
            # Note 1: we can also use `pyright-langserver --stdio` but it requires pyright to be installed with npm
            # Note 2: we can also use `bpyright-langserver --stdio` if we ever are unhappy with pyright
            ProcessLaunchInfo(cmd="python -m pyright.langserver --stdio", cwd=repository_root_path),
            "python",
        )

        # Event to signal when initial workspace analysis is complete
        self.analysis_complete = threading.Event()
        self.found_source_files = False

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["venv", "__pycache__"]

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Pyright Language Server.
        """
        # Create basic initialization parameters
        initialize_params: InitializeParams = {  # type: ignore
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
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True},
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {
                            "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]
                        },
                    },
                    "executeCommand": {"dynamicRegistration": True},
                },
                "textDocument": {
                    "synchronization": {"dynamicRegistration": True, "willSave": True, "willSaveWaitUntil": True, "didSave": True},
                    "completion": {
                        "dynamicRegistration": True,
                        "contextSupport": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                        },
                        "completionItemKind": {
                            "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
                        },
                    },
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
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {
                            "valueSet": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]
                        },
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
                                    "",
                                    "quickfix",
                                    "refactor",
                                    "refactor.extract",
                                    "refactor.inline",
                                    "refactor.rewrite",
                                    "source",
                                    "source.organizeImports",
                                ]
                            }
                        },
                    },
                    "codeLens": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "onTypeFormatting": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
            },
            "workspaceFolders": [
                {"uri": pathlib.Path(repository_absolute_path).as_uri(), "name": os.path.basename(repository_absolute_path)}
            ],
        }

        return initialize_params

    def _start_server(self):
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

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def window_log_message(msg):
            """
            Monitor Pyright's log messages to detect when initial analysis is complete.
            Pyright logs "Found X source files" when it finishes scanning the workspace.
            """
            message_text = msg.get("message", "")
            self.logger.log(f"LSP: window/logMessage: {message_text}", logging.INFO)

            # Look for "Found X source files" which indicates workspace scanning is complete
            # Unfortunately, pyright is unreliable and there seems to be no better way
            if re.search(r"Found \d+ source files?", message_text):
                self.logger.log("Pyright workspace scanning complete", logging.INFO)
                self.found_source_files = True
                self.analysis_complete.set()
                self.completions_available.set()

        def check_experimental_status(params):
            """
            Also listen for experimental/serverStatus as a backup signal
            """
            if params.get("quiescent") == True:
                self.logger.log("Received experimental/serverStatus with quiescent=true", logging.INFO)
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

        self.logger.log("Starting pyright-langserver server process", logging.INFO)
        self.server.start()

        # Send proper initialization parameters
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to pyright server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(f"Received initialize response from pyright server: {init_response}", logging.INFO)

        # Verify that the server supports our required features
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        # Complete the initialization handshake
        self.server.notify.initialized({})

        # Wait for Pyright to complete its initial workspace analysis
        # This prevents zombie processes by ensuring background tasks finish
        self.logger.log("Waiting for Pyright to complete initial workspace analysis...", logging.INFO)
        if self.analysis_complete.wait(timeout=5.0):
            self.logger.log("Pyright initial analysis complete, server ready", logging.INFO)
        else:
            self.logger.log("Timeout waiting for Pyright analysis completion, proceeding anyway", logging.WARNING)
            # Fallback: assume analysis is complete after timeout
            self.analysis_complete.set()
            self.completions_available.set()
