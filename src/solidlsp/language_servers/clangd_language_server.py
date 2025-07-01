"""
Provides C/C++ specific instantiation of the LanguageServer class. Contains various configurations and settings specific to C/C++.
"""

import json
import logging
import os
import pathlib
import stat
import threading

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import FileUtils, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


class ClangdLanguageServer(SolidLanguageServer):
    """
    Provides C/C++ specific instantiation of the LanguageServer class. Contains various configurations and settings specific to C/C++.
    As the project gets bigger in size, building index will take time. Try running clangd multiple times to ensure index is built properly.
    Also make sure compile_commands.json is created at root of the source directory. Check clangd test case for example.
    """

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
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
        self.server_ready = threading.Event()
        self.service_ready_event = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self.resolve_main_method_available = threading.Event()

    def setup_runtime_dependencies(self, logger: LanguageServerLogger, config: LanguageServerConfig) -> str:
        """
        Setup runtime dependencies for ClangdLanguageServer.
        """
        platform_id = PlatformUtils.get_platform_id()

        with open(os.path.join(os.path.dirname(__file__), "clangd_language_server", "runtime_dependencies.json")) as f:
            d = json.load(f)
            del d["_description"]

        assert platform_id.value in [
            "linux-x64",
            "win-x64",
            "osx-arm64",
        ], (
            "Unsupported platform: " + platform_id.value
        )

        runtime_dependencies = d["runtimeDependencies"]
        runtime_dependencies = [dependency for dependency in runtime_dependencies if dependency["platformId"] == platform_id.value]
        assert len(runtime_dependencies) == 1
        # Select dependency matching the current platform
        dependency = next((dep for dep in runtime_dependencies if dep["platformId"] == platform_id.value), None)
        if dependency is None:
            raise RuntimeError(f"No runtime dependency found for platform {platform_id.value}")

        clangd_ls_dir = os.path.join(os.path.dirname(__file__), "static", "clangd")
        clangd_executable_path = os.path.join(clangd_ls_dir, "clangd_19.1.2", "bin", dependency["binaryName"])
        if not os.path.exists(clangd_executable_path):
            clangd_url = dependency["url"]
            logger.log(f"Clangd executable not found at {clangd_executable_path}. Downloading from {clangd_url}", logging.INFO)
            os.makedirs(clangd_ls_dir, exist_ok=True)
            if dependency["archiveType"] == "zip":
                FileUtils.download_and_extract_archive(logger, clangd_url, clangd_ls_dir, dependency["archiveType"])
            else:
                raise RuntimeError(f"Unsupported archive type: {dependency['archiveType']}")
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
        with open(os.path.join(os.path.dirname(__file__), "clangd_language_server", "initialize_params.json")) as f:
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

    def _start_server(self):
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

        def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    self.resolve_main_method_available.set()
            return

        def lang_status_handler(params):
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def check_experimental_status(params):
            if params["quiescent"] == True:
                self.server_ready.set()

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        self.logger.log("Starting Clangd server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)
        assert init_response["capabilities"]["textDocumentSync"]["change"] == 2
        assert "completionProvider" in init_response["capabilities"]
        assert init_response["capabilities"]["completionProvider"] == {
            "triggerCharacters": [".", "<", ">", ":", '"', "/", "*"],
            "resolveProvider": False,
        }

        self.server.notify.initialized({})

        self.completions_available.set()
        # set ready flag
        self.server_ready.set()
        self.server_ready.wait()
