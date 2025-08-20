"""
Provides Svelte specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Svelte.
"""

import logging
import os
import pathlib
import shutil
import threading
from typing import Any

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings


class SvelteLanguageServer(SolidLanguageServer):
    """
    Provides Svelte specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Svelte.
    """

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a SvelteLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        svelte_lsp_executable_path = self._setup_runtime_dependencies(logger, config, solidlsp_settings)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=svelte_lsp_executable_path, cwd=repository_root_path),
            "svelte",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "build",
            "coverage",
            ".svelte-kit",
        ]

    @classmethod
    def _setup_runtime_dependencies(
        cls, logger: LanguageServerLogger, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> list[str]:
        """
        Setup runtime dependencies for Svelte Language Server and return the command to start the server.
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
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for Svelte language server at the moment"

        # Verify both node and npx are installed
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npx_installed = shutil.which("npx") is not None
        assert is_npx_installed, "npx is not installed or isn't in PATH. Please install npm and try again."

        # Always use npx to run svelte-proxy-lsp (it will auto-install if needed)
        logger.log("Using npx to run svelte-proxy-lsp@latest (will auto-install if needed)", logging.INFO)
        return ["npx", "--yes", "svelte-proxy-lsp@latest", "--stdio"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Svelte Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()

        # Find all tsconfig.json files to detect multiple projects
        workspace_folders = []
        tsconfig_paths = []

        # Walk through the repository to find tsconfig.json files
        for root, dirs, files in os.walk(repository_absolute_path):
            # Skip node_modules and other ignored directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["node_modules", "dist", "build"]]

            if "tsconfig.json" in files:
                project_path = root
                project_uri = pathlib.Path(project_path).as_uri()
                project_name = os.path.relpath(project_path, repository_absolute_path)
                if project_name == ".":
                    project_name = os.path.basename(repository_absolute_path)

                workspace_folders.append(
                    {
                        "uri": project_uri,
                        "name": project_name,
                    }
                )
                tsconfig_paths.append(project_path)

        # If no tsconfig.json found, use the repository root
        if not workspace_folders:
            workspace_folders = [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ]

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
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                    "configuration": True,
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": workspace_folders,
            "initializationOptions": {
                "configuration": {
                    "svelte": {"enable-ts-plugin": True, "format": {"enable": True}},
                    "typescript": {"enable": True, "diagnostics": {"enable": True}},
                    "javascript": {"enable": True},
                    "html": {"enable": True},
                    "css": {"enable": True},
                }
            },
        }
        return initialize_params

    def _start_server(self):
        """
        Starts the Svelte Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        """
        self.logger.log("Starting Svelte Language Server _start_server method", logging.INFO)

        def register_capability_handler(params: dict[str, Any]) -> Any:
            if "registrations" in params:
                for registration in params["registrations"]:
                    if registration["method"] == "workspace/executeCommand":
                        self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(params: dict[str, Any]) -> list[Any]:
            return []

        def do_nothing(params: dict[str, Any]) -> Any:
            return

        def window_log_message(msg: dict[str, Any]) -> None:
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def check_experimental_status(params: dict[str, Any]) -> None:
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

        self.logger.log("Starting Svelte server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # Svelte-specific capability checks
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        if self.server_ready.wait(timeout=2.0):
            self.logger.log("Svelte server is ready", logging.INFO)
        else:
            self.logger.log("Timeout waiting for Svelte server to become ready, proceeding anyway", logging.INFO)
            # Fallback: assume server is ready after timeout
            self.server_ready.set()
        self.completions_available.set()

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 1.5
