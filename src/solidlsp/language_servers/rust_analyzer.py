"""
Provides Rust specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Rust.
"""

import json
import logging
import os
import pathlib
import stat
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import FileUtils, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


class RustAnalyzer(SolidLanguageServer):
    """
    Provides Rust specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Rust.
    """

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        """
        Creates a RustAnalyzer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        rustanalyzer_executable_path = self.setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=rustanalyzer_executable_path, cwd=repository_root_path),
            "rust",
        )
        self.server_ready = threading.Event()
        self.service_ready_event = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self.resolve_main_method_available = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["target"]

    def setup_runtime_dependencies(self, logger: LanguageServerLogger, config: LanguageServerConfig) -> str:
        """
        Setup runtime dependencies for rust_analyzer.
        """
        platform_id = PlatformUtils.get_platform_id()

        with open(os.path.join(os.path.dirname(__file__), "rust_analyzer", "runtime_dependencies.json"), encoding="utf-8") as f:
            d = json.load(f)
            del d["_description"]

        # assert platform_id.value in [
        #     "linux-x64",
        #     "win-x64",
        # ], "Only linux-x64 and win-x64 platform is supported for in multilspy at the moment"

        runtime_dependencies = d["runtimeDependencies"]
        runtime_dependencies = [dependency for dependency in runtime_dependencies if dependency["platformId"] == platform_id.value]
        assert len(runtime_dependencies) == 1
        dependency = runtime_dependencies[0]

        rustanalyzer_ls_dir = os.path.join(os.path.dirname(__file__), "static", "RustAnalyzer")
        rustanalyzer_executable_path = os.path.join(rustanalyzer_ls_dir, dependency["binaryName"])
        if not os.path.exists(rustanalyzer_ls_dir):
            os.makedirs(rustanalyzer_ls_dir)
            if dependency["archiveType"] == "gz":
                FileUtils.download_and_extract_archive(logger, dependency["url"], rustanalyzer_executable_path, dependency["archiveType"])
            else:
                FileUtils.download_and_extract_archive(logger, dependency["url"], rustanalyzer_ls_dir, dependency["archiveType"])
        assert os.path.exists(rustanalyzer_executable_path)
        os.chmod(rustanalyzer_executable_path, stat.S_IEXEC)

        return rustanalyzer_executable_path

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Rust Analyzer Language Server.
        """
        with open(os.path.join(os.path.dirname(__file__), "rust_analyzer", "initialize_params.json"), encoding="utf-8") as f:
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
        Starts the Rust Analyzer Language Server
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

        self.logger.log("Starting RustAnalyzer server process", logging.INFO)
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
            "resolveProvider": True,
            "triggerCharacters": [":", ".", "'", "("],
            "completionItem": {"labelDetailsSupport": True},
        }
        self.server.notify.initialized({})
        self.completions_available.set()

        self.server_ready.wait()
