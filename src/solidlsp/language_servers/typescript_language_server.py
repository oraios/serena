"""
Provides TypeScript specific instantiation of the LanguageServer class. Contains various configurations and settings specific to TypeScript.
"""

import logging
import os
import pathlib
import threading
from time import sleep

from overrides import override
from sensai.util.logging import LogTime

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo

from .common import NodeJsUtils, RuntimeDependency, RuntimeDependencyCollection

# Platform-specific imports
if os.name != "nt":  # Unix-like systems
    import pwd
else:
    # Dummy pwd module for Windows
    class pwd:
        @staticmethod
        def getpwuid(uid):
            return type("obj", (), {"pw_name": os.environ.get("USERNAME", "unknown")})()


# Conditionally import pwd module (Unix-only)
if not PlatformUtils.get_platform_id().value.startswith("win"):
    pass


class TypeScriptLanguageServer(SolidLanguageServer):
    """
    Provides TypeScript specific instantiation of the LanguageServer class. Contains various configurations and settings specific to TypeScript.
    """

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        """
        Creates a TypeScriptLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        ts_lsp_executable_path = self._setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=ts_lsp_executable_path, cwd=repository_root_path),
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
    def _setup_runtime_dependencies(cls, logger: LanguageServerLogger, config: LanguageServerConfig) -> list[str]:
        """
        Setup runtime dependencies for TypeScript Language Server and return the command to start the server.
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
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for multilspy javascript/typescript at the moment"

        # Verify both node and npm are installed using NodeJsUtils
        node_executable = NodeJsUtils.find_node_executable()
        assert node_executable is not None, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        npm_cli_script = NodeJsUtils.get_npm_cli_script_path()
        assert npm_cli_script is not None, "npm CLI script not found. Please ensure npm is properly installed."

        # Create dependencies using direct node execution
        typescript_install_cmd = NodeJsUtils.build_npm_install_command(["install", "--prefix", "./", "typescript@5.5.4"])
        tsserver_install_cmd = NodeJsUtils.build_npm_install_command(["install", "--prefix", "./", "typescript-language-server@4.3.3"])

        assert typescript_install_cmd is not None, "Failed to build TypeScript install command"
        assert tsserver_install_cmd is not None, "Failed to build TypeScript Language Server install command"

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="typescript",
                    description="typescript package",
                    command=typescript_install_cmd,
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript-language-server",
                    description="typescript-language-server package",
                    command=tsserver_install_cmd,
                    platform_id="any",
                ),
            ]
        )

        # Install typescript and typescript-language-server if not already installed
        tsserver_ls_dir = os.path.join(cls.ls_resources_dir(), "ts-lsp")
        tsserver_script_path = os.path.join(tsserver_ls_dir, "node_modules", "typescript-language-server", "lib", "cli.mjs")

        if not os.path.exists(tsserver_script_path):
            logger.log(f"Typescript Language Server script not found at {tsserver_script_path}. Installing...", logging.INFO)
            with LogTime("Installation of TypeScript language server dependencies", logger=logger.logger):
                deps.install(logger, tsserver_ls_dir)

        if not os.path.exists(tsserver_script_path):
            raise FileNotFoundError(
                f"typescript-language-server script not found at {tsserver_script_path}, something went wrong with the installation."
            )

        tsserver_command = NodeJsUtils.build_node_command(node_executable, tsserver_script_path, ["--stdio"])

        return tsserver_command

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the TypeScript Language Server.
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
        Starts the TypeScript Language Server, waits for the server to be ready and yields the LanguageServer instance.

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
                    # TypeScript doesn't have a direct equivalent to resolve_main_method
                    # You might want to set a different flag or remove this line
                    # self.resolve_main_method_available.set()
            return

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def check_experimental_status(params):
            """
            Also listen for experimental/serverStatus as a backup signal
            """
            if params.get("quiescent") == True:
                self.server_ready.set()
                self.completions_available.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        self.logger.log("Starting TypeScript server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # TypeScript-specific capability checks
        assert init_response["capabilities"]["textDocumentSync"] == 2
        assert "completionProvider" in init_response["capabilities"]
        assert init_response["capabilities"]["completionProvider"] == {
            "triggerCharacters": [".", '"', "'", "/", "@", "<"],
            "resolveProvider": True,
        }

        self.server.notify.initialized({})
        if self.server_ready.wait(timeout=1.0):
            self.logger.log("TypeScript server is ready", logging.INFO)
        else:
            self.logger.log("Timeout waiting for TypeScript server to become ready, proceeding anyway", logging.INFO)
            # Fallback: assume server is ready after timeout
            self.server_ready.set()
        self.completions_available.set()

    @override
    # For some reason, the LS may need longer to process this, so we just retry
    def _send_references_request(self, relative_file_path: str, line: int, column: int):
        # TODO: The LS doesn't return references contained in other files if it doesn't sleep. This is
        #   despite the LS having processed requests already. I don't know what causes this, but sleeping
        #   one second helps. It may be that sleeping only once is enough but that's hard to reliably test.
        #   It may be that even this 1sec is not enough in larger TS projects, at some point we should find what
        #   causes this and solve it.
        sleep(1)
        return super()._send_references_request(relative_file_path, line, column)
