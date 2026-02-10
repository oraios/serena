"""
Provides Bash specific instantiation of the LanguageServer class using bash-language-server.
Contains various configurations and settings specific to Bash scripting.
"""

import logging
import os
import pathlib
import shutil
import threading

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class BashLanguageServer(SolidLanguageServer):
    """
    Provides Bash specific instantiation of the LanguageServer class using bash-language-server.
    Contains various configurations and settings specific to Bash scripting.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a BashLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        bash_lsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=bash_lsp_executable_path, cwd=repository_root_path),
            "bash",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Bash Language Server and return the command to start the server.
        """
        # Verify both node and npm are installed
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="bash-language-server",
                    description="bash-language-server package",
                    command="npm install --prefix ./ bash-language-server@5.6.0",
                    platform_id="any",
                ),
            ]
        )

        # Install bash-language-server if not already installed
        bash_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "bash-lsp")
        bash_executable_path = os.path.join(bash_ls_dir, "node_modules", ".bin", "bash-language-server")

        # Handle Windows executable extension
        if os.name == "nt":
            bash_executable_path += ".cmd"

        if not os.path.exists(bash_executable_path):
            log.info(f"Bash Language Server executable not found at {bash_executable_path}. Installing...")
            deps.install(bash_ls_dir)
            log.info("Bash language server dependencies installed successfully")

        if not os.path.exists(bash_executable_path):
            raise FileNotFoundError(
                f"bash-language-server executable not found at {bash_executable_path}, something went wrong with the installation."
            )
        return f"{bash_executable_path} start"

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Bash Language Server.
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
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
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
        Starts the Bash Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            # Check for bash-language-server ready signals
            message_text = msg.get("message", "")
            if "Analyzing" in message_text or "analysis complete" in message_text.lower():
                log.info("Bash language server analysis signals detected")
                self.server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Bash server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from bash server: {init_response}")

        # Enhanced capability checks for bash-language-server 5.6.0
        assert init_response["capabilities"]["textDocumentSync"] in [1, 2]  # Full or Incremental
        assert "completionProvider" in init_response["capabilities"]

        # Verify document symbol support is available
        if "documentSymbolProvider" in init_response["capabilities"]:
            log.info("Bash server supports document symbols")
        else:
            log.warning("Warning: Bash server does not report document symbol support")

        self.server.notify.initialized({})

        # Wait for server readiness with timeout
        log.info("Waiting for Bash language server to be ready...")
        if not self.server_ready.wait(timeout=3.0):
            # Fallback: assume server is ready after timeout
            # This is common. bash-language-server doesn't always send explicit ready signals. Log as info
            log.info("Timeout waiting for bash server ready signal, proceeding anyway")
            self.server_ready.set()
        else:
            log.info("Bash server initialization complete")

    def request_document_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None) -> DocumentSymbols:
        # Uses the standard LSP documentSymbol request which provides reliable function detection
        # for all bash function syntaxes including:
        # - function name() { ... } (with function keyword)
        # - name() { ... } (traditional syntax)
        # - Functions with various indentation levels
        # - Functions with comments before/after/inside

        log.debug(f"Requesting document symbols via LSP for {relative_file_path}")

        # Use the standard LSP approach - bash-language-server handles all function syntaxes correctly
        document_symbols = super().request_document_symbols(relative_file_path, file_buffer=file_buffer)

        # Log detection results for debugging
        functions = [s for s in document_symbols.iter_symbols() if s.get("kind") == 12]
        log.info(f"LSP function detection for {relative_file_path}: Found {len(functions)} functions")

        return document_symbols
