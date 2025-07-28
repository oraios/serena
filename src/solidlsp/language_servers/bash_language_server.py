"""
Provides Bash specific instantiation of the LanguageServer class using bash-language-server.
Contains various configurations and settings specific to Bash scripting.
"""

import logging
import os
import pathlib
import shutil
import threading

from overrides import override

from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class BashLanguageServer(SolidLanguageServer):
    """
    Provides Bash specific instantiation of the LanguageServer class using bash-language-server.
    Contains various configurations and settings specific to Bash scripting.
    """

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a BashLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        bash_lsp_executable_path = self._setup_runtime_dependencies(logger, config, solidlsp_settings)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=bash_lsp_executable_path, cwd=repository_root_path),
            "bash",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            ".cache",
            "tmp",
            "temp",
        ]

    @classmethod
    def _setup_runtime_dependencies(
        cls, logger: LanguageServerLogger, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> str:
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
                    command="npm install --prefix ./ bash-language-server@5.4.0",
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
            logger.log(f"Bash Language Server executable not found at {bash_executable_path}. Installing...", logging.INFO)
            deps.install(logger, bash_ls_dir)
            logger.log("Bash language server dependencies installed successfully", logging.INFO)

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
        return initialize_params

    def _start_server(self):
        """
        Starts the Bash Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting Bash server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # Bash-specific capability checks
        assert init_response["capabilities"]["textDocumentSync"] in [1, 2]  # Full or Incremental
        assert "completionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # Set server ready immediately as bash-language-server doesn't have a specific ready signal
        self.server_ready.set()
        self.completions_available.set()

        self.logger.log("Bash server is ready", logging.INFO)
