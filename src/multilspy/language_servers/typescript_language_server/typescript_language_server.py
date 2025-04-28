"""
Provides TypeScript specific instantiation of the LanguageServer class. Contains various configurations and settings specific to TypeScript.
"""

import asyncio
import json
import shutil
import logging
import os
import subprocess
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator, Tuple

from overrides import override

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_utils import PlatformUtils, PlatformId

# Platform-specific imports
if os.name != 'nt':  # Unix-like systems
    import pwd
else:
    # Dummy pwd module for Windows
    class pwd:
        @staticmethod
        def getpwuid(uid):
            return type('obj', (), {'pw_name': os.environ.get('USERNAME', 'unknown')})()


# Conditionally import pwd module (Unix-only)
if not PlatformUtils.get_platform_id().value.startswith("win"):
    import pwd


class TypeScriptLanguageServer(LanguageServer):
    """
    Provides TypeScript specific instantiation of the LanguageServer class. Contains various configurations and settings specific to TypeScript.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a TypeScriptLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        ts_lsp_executable_path = self.setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=ts_lsp_executable_path, cwd=repository_root_path),
            "typescript",
        )
        self.server_ready = asyncio.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
        ]

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> str:
        """
        Setup runtime dependencies for TypeScript Language Server.
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

        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            del d["_description"]

        runtime_dependencies = d.get("runtimeDependencies", [])
        tsserver_ls_dir = os.path.join(os.path.dirname(__file__), "static", "ts-lsp")
        tsserver_executable_path = os.path.join(tsserver_ls_dir, "typescript-language-server")

        # Verify both node and npm are installed
        is_node_installed = shutil.which('node') is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which('npm') is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        # Install typescript and typescript-language-server if not already installed
        if not os.path.exists(tsserver_ls_dir):
            os.makedirs(tsserver_ls_dir, exist_ok=True)
            for dependency in runtime_dependencies:
                # Windows doesn't support the 'user' parameter and doesn't have pwd module
                if PlatformUtils.get_platform_id().value.startswith("win"):
                    subprocess.run(
                        dependency["command"],
                        shell=True,
                        check=True,
                        cwd=tsserver_ls_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                else:
                    # On Unix-like systems, run as non-root user
                    user = pwd.getpwuid(os.getuid()).pw_name
                    subprocess.run(
                        dependency["command"],
                        shell=True,
                        check=True,
                        user=user,
                        cwd=tsserver_ls_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
        
        tsserver_executable_path = os.path.join(tsserver_ls_dir, "node_modules", ".bin", "typescript-language-server")

        assert os.path.exists(tsserver_executable_path), "typescript-language-server executable not found. Please install typescript-language-server and try again."
        return f"{tsserver_executable_path} --stdio"

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the TypeScript Language Server.
        """
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r") as f:
            d = json.load(f)

        del d["_description"]

        d["processId"] = os.getpid()
        assert d["rootPath"] == "$rootPath"
        d["rootPath"] = repository_absolute_path

        assert d["rootUri"] == "$rootUri"
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["uri"] == "$uri"
        d["workspaceFolders"][0]["uri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["name"] == "$name"
        d["workspaceFolders"][0]["name"] = os.path.basename(repository_absolute_path)

        return d

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["TypeScriptLanguageServer"]:
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

        async def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    # TypeScript doesn't have a direct equivalent to resolve_main_method
                    # You might want to set a different flag or remove this line
                    # self.resolve_main_method_available.set()
            return

        async def execute_client_command_handler(params):
            return []

        async def do_nothing(params):
            return

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        async with super().start_server():
            self.logger.log("Starting TypeScript server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)

            # TypeScript-specific capability checks
            assert init_response["capabilities"]["textDocumentSync"] == 2
            assert "completionProvider" in init_response["capabilities"]
            assert init_response["capabilities"]["completionProvider"] == {
                "triggerCharacters": ['.', '"', "'", '/', '@', '<'],
                "resolveProvider": True
            }

            self.server.notify.initialized({})
            self.completions_available.set()

            # TypeScript server is typically ready immediately after initialization
            self.server_ready.set()
            await self.server_ready.wait()

            yield self

            await self.server.shutdown()
            await self.server.stop()
