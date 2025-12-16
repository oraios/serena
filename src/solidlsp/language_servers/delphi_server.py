"""
Provides Delphi specific instantiation of the LanguageServer class using DelphiLSP.
Contains various configurations and settings specific to Delphi and RAD Studio.
"""

import logging
import os
import pathlib
import shutil
import threading
from typing import Optional

from solidlsp.language_servers.common import quote_windows_path
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class DelphiLanguageServer(SolidLanguageServer):
    """
    Provides Delphi specific instantiation of the LanguageServer class using DelphiLSP.
    Contains various configurations and settings specific to Delphi and RAD Studio.

    DelphiLSP is provided by Embarcadero as part of RAD Studio 11.0 or later.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a DelphiLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        delphilsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=delphilsp_executable_path, cwd=repository_root_path),
            "delphi",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.completions_available_event = threading.Event()

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Delphi Language Server (DelphiLSP) and return the command to start the server.

        This method will:
        1. Check if DelphiLSP.exe is in PATH
        2. Check common RAD Studio installation locations
        3. Raise an error if not found (requires RAD Studio 11.0+)

        Returns:
            str: The path to the DelphiLSP.exe executable
        """
        # First, check if DelphiLSP is already in PATH
        delphilsp_in_path = shutil.which("DelphiLSP")
        if delphilsp_in_path:
            log.info(f"Found DelphiLSP in PATH: {delphilsp_in_path}")
            return quote_windows_path(delphilsp_in_path)

        # Check common RAD Studio installation locations
        # RAD Studio typically installs to C:\Program Files (x86)\Embarcadero\Studio\<version>\bin
        common_locations = [
            r"C:\Program Files (x86)\Embarcadero\Studio\23.0\bin\DelphiLSP.exe",  # RAD Studio 12
            r"C:\Program Files (x86)\Embarcadero\Studio\22.0\bin\DelphiLSP.exe",  # RAD Studio 11
            r"C:\Program Files\Embarcadero\Studio\23.0\bin\DelphiLSP.exe",
            r"C:\Program Files\Embarcadero\Studio\22.0\bin\DelphiLSP.exe",
        ]

        for path in common_locations:
            if os.path.exists(path):
                log.info(f"Found DelphiLSP at: {path}")
                return quote_windows_path(path)

        # Try to find it using BDS environment variable
        bds_path = os.environ.get("BDS")
        if bds_path:
            delphilsp_path = os.path.join(bds_path, "bin", "DelphiLSP.exe")
            if os.path.exists(delphilsp_path):
                log.info(f"Found DelphiLSP using BDS environment variable: {delphilsp_path}")
                return quote_windows_path(delphilsp_path)

        raise FileNotFoundError(
            "DelphiLSP.exe not found. DelphiLSP requires RAD Studio 11.0 or later. "
            "Please install RAD Studio or add DelphiLSP.exe to PATH. "
            "See: https://docwiki.embarcadero.com/RADStudio/Alexandria/en/Using_DelphiLSP_Code_Insight_with_Other_Editors"
        )

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Delphi Language Server.

        DelphiLSP supports custom initialization options including:
        - serverType: "controller", "agent", or "linter"
        - agentCount: Number of agent processes (for controller mode)
        - returnDccFlags, returnHoverModel: Response format options
        - storeProjectSettings: Whether to save .delphilsp.json
        - enableFileWatcher: Monitor file changes
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {
                        "didSave": True,
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "preselectSupport": True,
                            "insertReplaceSupport": True,
                        },
                        "contextSupport": True,
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {
                                "labelOffsetSupport": True,
                            },
                        },
                        "contextSupport": True,
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentHighlight": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "labelSupport": True,
                    },
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
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
                        "isPreferredSupport": True,
                        "dataSupport": True,
                    },
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "rename": {
                        "dynamicRegistration": True,
                        "prepareSupport": True,
                    },
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "tagSupport": {"valueSet": [1, 2]},
                        "versionSupport": True,
                    },
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "executeCommand": {"dynamicRegistration": True},
                    "configuration": True,
                    "workspaceEdit": {
                        "documentChanges": True,
                        "resourceOperations": ["create", "rename", "delete"],
                    },
                    "didChangeWatchedFiles": {"dynamicRegistration": True},
                },
                "window": {
                    "workDoneProgress": True,
                },
            },
            "initializationOptions": {
                # Use "controller" mode with multiple agents for better performance
                "serverType": "controller",
                "agentCount": 2,  # Number of parallel processing agents
                "returnDccFlags": True,
                "returnHoverModel": True,
                "storeProjectSettings": False,  # Don't auto-create .delphilsp.json
                "enableFileWatcher": True,
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
        Starts the Delphi Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        def register_capability_handler(params: dict) -> None:
            log.debug(f"Capability registered: {params}")
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            # Mark server as ready when we see initialization messages
            message_text = msg.get("message", "")
            if any(keyword in message_text.lower() for keyword in ["initialized", "ready", "started"]):
                log.info("Delphi language server ready signal detected")
                self.server_ready.set()
                self.completions_available.set()

        def window_show_message(msg: dict) -> None:
            log.info(f"LSP: window/showMessage: {msg}")

        def publish_diagnostics(params: dict) -> None:
            log.debug(f"Diagnostics published for {params.get('uri', 'unknown')}")
            # Mark server as operational once diagnostics start coming in
            if not self.server_ready.is_set():
                log.info("Received diagnostics, marking server as ready")
                self.server_ready.set()
                self.completions_available.set()

        def progress_notification(params: dict) -> None:
            log.debug(f"Progress: {params}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_show_message)
        self.server.on_notification("textDocument/publishDiagnostics", publish_diagnostics)
        self.server.on_notification("$/progress", progress_notification)

        log.info("Starting Delphi server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Delphi server: {init_response}")

        # Verify capabilities
        capabilities = init_response.get("capabilities", {})

        # DelphiLSP provides comprehensive capabilities
        if "textDocumentSync" in capabilities:
            log.info("Delphi server supports text document synchronization")
        if "completionProvider" in capabilities:
            log.info("Delphi server supports code completion")
        if "definitionProvider" in capabilities:
            log.info("Delphi server supports go to definition")
        if "referencesProvider" in capabilities:
            log.info("Delphi server supports find references")
        if "documentSymbolProvider" in capabilities:
            log.info("Delphi server supports document symbols")
        if "hoverProvider" in capabilities:
            log.info("Delphi server supports hover information")

        self.server.notify.initialized({})

        # Wait for server readiness with timeout
        log.info("Waiting for Delphi language server to be ready...")
        if not self.server_ready.wait(timeout=10.0):
            # DelphiLSP may take longer to initialize, especially in controller mode
            log.info("Timeout waiting for Delphi server ready signal, assuming server is ready")
            self.server_ready.set()
            self.completions_available.set()
        else:
            log.info("Delphi server initialization complete")

    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        Check if a directory should be ignored for Delphi projects.
        Common Delphi/RAD Studio directories to ignore.
        """
        ignored_dirs = {
            "__history",
            "__recovery",
            "win32",
            "win64",
            "debug",
            "release",
            "lib",
            "dcu",
            "obj",
            ".git",
            ".svn",
            ".hg",
            "node_modules",
            "packages",  # Delphi packages output
        }
        return dirname.lower() in ignored_dirs

    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        """
        Request document symbols for a Delphi file.
        """
        log.debug(f"Requesting document symbols for Delphi file: {relative_file_path}")
        document_symbols = super().request_document_symbols(relative_file_path, file_buffer=file_buffer)

        # Log what we found for debugging
        symbols_list = list(document_symbols.iter_symbols())
        log.info(f"Found {len(symbols_list)} symbols in {relative_file_path}")

        return document_symbols
