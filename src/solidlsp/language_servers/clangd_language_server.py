"""
Provides C/C++ specific instantiation of the LanguageServer class. Contains various configurations and settings specific to C/C++.
"""

import logging
import os
import pathlib
import threading
from typing import Any, cast

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)


class ClangdLanguageServer(SolidLanguageServer):
    """
    Provides C/C++ specific instantiation of the LanguageServer class. Contains various configurations and settings specific to C/C++.
    As the project gets bigger in size, building index will take time. Try running clangd multiple times to ensure index is built properly.
    Also make sure compile_commands.json is created at root of the source directory. Check clangd test case for example.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a ClangdLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        super().__init__(config, repository_root_path, None, "cpp", solidlsp_settings)
        self.server_ready = threading.Event()
        self.service_ready_event = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self.resolve_main_method_available = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for ClangdLanguageServer and return the path to the executable.
            """
            import shutil

            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="Clangd",
                        description="Clangd for Linux (x64)",
                        url="https://github.com/clangd/clangd/releases/download/19.1.2/clangd-linux-19.1.2.zip",
                        platform_id="linux-x64",
                        archive_type="zip",
                        binary_name="clangd_19.1.2/bin/clangd",
                    ),
                    RuntimeDependency(
                        id="Clangd",
                        description="Clangd for Windows (x64)",
                        url="https://github.com/clangd/clangd/releases/download/19.1.2/clangd-windows-19.1.2.zip",
                        platform_id="win-x64",
                        archive_type="zip",
                        binary_name="clangd_19.1.2/bin/clangd.exe",
                    ),
                    RuntimeDependency(
                        id="Clangd",
                        description="Clangd for macOS (x64)",
                        url="https://github.com/clangd/clangd/releases/download/19.1.2/clangd-mac-19.1.2.zip",
                        platform_id="osx-x64",
                        archive_type="zip",
                        binary_name="clangd_19.1.2/bin/clangd",
                    ),
                    RuntimeDependency(
                        id="Clangd",
                        description="Clangd for macOS (Arm64)",
                        url="https://github.com/clangd/clangd/releases/download/19.1.2/clangd-mac-19.1.2.zip",
                        platform_id="osx-arm64",
                        archive_type="zip",
                        binary_name="clangd_19.1.2/bin/clangd",
                    ),
                ]
            )

            clangd_ls_dir = os.path.join(self._ls_resources_dir, "clangd")

            try:
                dep = deps.get_single_dep_for_current_platform()
            except RuntimeError:
                dep = None

            if dep is None:
                # No prebuilt binary available, look for system-installed clangd
                clangd_executable_path = shutil.which("clangd")
                if not clangd_executable_path:
                    raise FileNotFoundError(
                        "Clangd is not installed on your system.\n"
                        + "Please install clangd using your system package manager:\n"
                        + "  Ubuntu/Debian: sudo apt-get install clangd\n"
                        + "  Fedora/RHEL: sudo dnf install clang-tools-extra\n"
                        + "  Arch Linux: sudo pacman -S clang\n"
                        + "See https://clangd.llvm.org/installation for more details."
                    )
                log.info(f"Using system-installed clangd at {clangd_executable_path}")
            else:
                # Standard download and install for platforms with prebuilt binaries
                clangd_executable_path = deps.binary_path(clangd_ls_dir)
                if not os.path.exists(clangd_executable_path):
                    log.info(f"Clangd executable not found at {clangd_executable_path}. Downloading from {dep.url}")
                    _ = deps.install(clangd_ls_dir)
                if not os.path.exists(clangd_executable_path):
                    raise FileNotFoundError(
                        f"Clangd executable not found at {clangd_executable_path}.\n"
                        + "Make sure you have installed clangd. See https://clangd.llvm.org/installation"
                    )
                os.chmod(clangd_executable_path, 0o755)
            return clangd_executable_path

        def _create_launch_command(self, core_path: str) -> list[str] | str:
            return [core_path]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the clangd Language Server.
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
                    },
                },
                "workspace": {"workspaceFolders": True, "didChangeConfiguration": {"dynamicRegistration": True}},
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": "$name",
                }
            ],
        }

        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
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

        def register_capability_handler(params: Any) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    self.resolve_main_method_available.set()
            return

        def lang_status_handler(params: Any) -> None:
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        def execute_client_command_handler(params: Any) -> list:
            return []

        def do_nothing(params: Any) -> None:
            return

        def check_experimental_status(params: Any) -> None:
            if params["quiescent"] == True:
                self.server_ready.set()

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        log.info("Starting Clangd server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        assert init_response["capabilities"]["textDocumentSync"]["change"] == 2  # type: ignore
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
