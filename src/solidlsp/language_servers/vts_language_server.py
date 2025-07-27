"""
Language Server implementation for TypeScript/JavaScript using https://github.com/yioneko/vtsls,
which provides TypeScript language server functionality via VSCode's TypeScript extension
(contrary to typescript-language-server, which uses the TypeScript compiler directly).
"""

import logging
import os
import pathlib
import threading
from time import sleep

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo

from .common import NodeJsUtils, RuntimeDependency, RuntimeDependencyCollection


class VtsLanguageServer(SolidLanguageServer):
    """
    Provides TypeScript specific instantiation of the LanguageServer class using vtsls.
    Contains various configurations and settings specific to TypeScript via vtsls wrapper.
    """

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        """
        Creates a VtsLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        vts_lsp_executable_path = self._setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=vts_lsp_executable_path, cwd=repository_root_path),
            "typescript",
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
        ]

    @classmethod
    def _setup_runtime_dependencies(cls, logger: LanguageServerLogger, config: LanguageServerConfig) -> str:
        """
        Setup runtime dependencies for VTS Language Server and return the command to start the server.
        """
        platform_id = PlatformUtils.get_platform_id()

        valid_platforms = [
            PlatformId.LINUX_x64,
            PlatformId.LINUX_arm64,
            PlatformId.OSX,
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
            PlatformId.WIN_x64,
            PlatformId.WIN_arm64,
        ]
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for vtsls at the moment"

        # Verify both node and npm are installed using NodeJsUtils
        node_executable = NodeJsUtils.find_node_executable()
        assert node_executable is not None, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        npm_cli_script = NodeJsUtils.get_npm_cli_script_path()
        assert npm_cli_script is not None, "npm CLI script not found. Please ensure npm is properly installed."

        # Create dependencies using direct node execution
        vtsls_install_cmd = NodeJsUtils.build_npm_install_command(["install", "--prefix", "./", "@vtsls/language-server@0.2.9"])
        assert vtsls_install_cmd is not None, "Failed to build VTSLS install command"

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="vtsls",
                    description="vtsls language server package",
                    command=vtsls_install_cmd,
                    platform_id="any",
                ),
            ]
        )
        vts_ls_dir = os.path.join(cls.ls_resources_dir(), "vts-lsp")

        # Install vtsls if not already installed
        vts_script_path = os.path.join(vts_ls_dir, "node_modules", "@vtsls", "language-server", "bin", "vtsls")

        if not os.path.exists(vts_script_path):
            os.makedirs(vts_ls_dir, exist_ok=True)
            logger.log(f"VTSLS script not found at {vts_script_path}. Installing...", logging.INFO)
            deps.install(logger, vts_ls_dir)

        if not os.path.exists(vts_script_path):
            raise FileNotFoundError(f"vtsls script not found at {vts_script_path}, something went wrong with the installation.")

        # Build direct node command for vtsls
        vts_command = NodeJsUtils.build_node_command(node_executable, vts_script_path, ["--stdio"])

        # Use appropriate quoting for the platform
        if PlatformUtils.get_platform_id().value.startswith("win"):
            import subprocess

            return subprocess.list2cmdline(vts_command)
        else:
            import shlex

            return shlex.join(vts_command)

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the VTS Language Server.
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
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                    "configuration": True,  # This might be needed for vtsls
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
        Starts the VTS Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        """

        def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(params):
            return []

        def workspace_configuration_handler(params):
            # VTS may request workspace configuration
            # Return empty configuration for each requested item
            if "items" in params:
                return [{}] * len(params["items"])
            return {}

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def check_experimental_status(params):
            """
            Also listen for experimental/serverStatus as a backup signal
            """
            if params.get("quiescent") is True:
                self.server_ready.set()
                self.completions_available.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        self.logger.log("Starting VTS server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # VTS-specific capability checks
        # Be more flexible with capabilities since vtsls might have different structure
        self.logger.log(f"VTS init response capabilities: {init_response['capabilities']}", logging.DEBUG)

        # Basic checks to ensure essential capabilities are present
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]

        # Log the actual values for debugging
        self.logger.log(f"textDocumentSync: {init_response['capabilities']['textDocumentSync']}", logging.DEBUG)
        self.logger.log(f"completionProvider: {init_response['capabilities']['completionProvider']}", logging.DEBUG)

        self.server.notify.initialized({})
        if self.server_ready.wait(timeout=1.0):
            self.logger.log("VTS server is ready", logging.INFO)
        else:
            self.logger.log("Timeout waiting for VTS server to become ready, proceeding anyway", logging.INFO)
            # Fallback: assume server is ready after timeout
            self.server_ready.set()
        self.completions_available.set()

    # VTS may need longer to process references, so we include a sleep similar to TypeScript LS
    @override
    def _send_references_request(self, relative_file_path: str, line: int, column: int):
        sleep(1)
        return super()._send_references_request(relative_file_path, line, column)
