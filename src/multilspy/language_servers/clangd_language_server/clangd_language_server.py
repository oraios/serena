"""
Provides C/C++ specific instantiation of the LanguageServer class. Contains various configurations and settings specific to C/C++.
"""

import asyncio
import json
import logging
import os
import stat
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_utils import FileUtils
from multilspy.multilspy_utils import PlatformUtils


class ClangdLanguageServer(LanguageServer):
    """
    Provides C/C++ specific instantiation of the LanguageServer class. Contains various configurations and settings specific to C/C++.
    As the project gets bigger in size, building index will take time. Try running clangd multiple times to ensure index is built properly.
    Also make sure compile_commands.json is created at root of the source directory. Check clangd test case for example.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a ClangdLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        clangd_executable_path = self.setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=clangd_executable_path, cwd=repository_root_path),
            "cpp",
        )
        self.server_ready = asyncio.Event()

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> str:
        """
        Setup runtime dependencies for ClangdLanguageServer.
        """
        platform_id = PlatformUtils.get_platform_id()

        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            del d["_description"]

        assert platform_id.value in [
            "linux-x64"
        ], "Only linux-x64 is supported for in multilspy at the moment"

        runtime_dependencies = d["runtimeDependencies"]
        runtime_dependencies = [
            dependency for dependency in runtime_dependencies if dependency["platformId"] == platform_id.value
        ]
        assert len(runtime_dependencies) == 1
        dependency = runtime_dependencies[0]

        clangd_ls_dir = os.path.join(os.path.dirname(__file__), "static/clangd")
        clangd_executable_path = os.path.join(clangd_ls_dir, "clangd_19.1.2", "bin", dependency["binaryName"])
        if not os.path.exists(clangd_executable_path):
            clangd_url = dependency["url"]
            logger.log(f"Clangd executable not found at {clangd_executable_path}. Downloading from {clangd_url}", logging.INFO)
            os.makedirs(clangd_ls_dir, exist_ok=True)
            if dependency["archiveType"] == "zip":
                FileUtils.download_and_extract_archive(
                    logger, clangd_url, clangd_ls_dir, dependency["archiveType"]
                )
        if not os.path.exists(clangd_executable_path):
            raise FileNotFoundError(
                f"Clangd executable not found at {clangd_executable_path}.\n"
                "Make sure you have installed clangd. See https://clangd.llvm.org/installation"
            )
        os.chmod(clangd_executable_path, stat.S_IEXEC)

        return clangd_executable_path

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the clangd Language Server.
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
    async def start_server(self) -> AsyncIterator["ClangdLanguageServer"]:
        """
        Starts the Clangd Language Server, waits for the server to be ready and yields the LanguageServer instance.

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
                    self.resolve_main_method_available.set()
            return

        async def lang_status_handler(params):
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        async def execute_client_command_handler(params):
            return []

        async def do_nothing(params):
            return

        async def check_experimental_status(params):
            if params["quiescent"] == True:
                self.server_ready.set()

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        async with super().start_server():
            self.logger.log("Starting Clangd server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)
            assert init_response["capabilities"]["textDocumentSync"]["change"] == 2
            assert "completionProvider" in init_response["capabilities"]          
            assert init_response["capabilities"]["completionProvider"] == {
                "triggerCharacters": ['.', '<', '>', ':', '"', '/', '*'],
                "resolveProvider": False,
            }

            self.server.notify.initialized({})

            self.completions_available.set()
            # set ready flag
            self.server_ready.set()
            await self.server_ready.wait()

            yield self

            await self.server.shutdown()
            await self.server.stop()
