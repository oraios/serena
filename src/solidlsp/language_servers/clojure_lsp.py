"""
Provides Clojure specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Clojure.
"""

import logging
import os
import pathlib
import shutil
import subprocess
import threading
from typing import cast

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)


def run_command(cmd: list, capture_output: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, stdout=subprocess.PIPE if capture_output else None, stderr=subprocess.STDOUT if capture_output else None, text=True, check=True
    )


def verify_clojure_cli() -> None:
    install_msg = "Please install the official Clojure CLI from:\n  https://clojure.org/guides/getting_started"
    if shutil.which("clojure") is None:
        raise FileNotFoundError("`clojure` not found.\n" + install_msg)

    help_proc = run_command(["clojure", "--help"])
    if "-Aaliases" not in help_proc.stdout:
        raise RuntimeError("Detected a Clojure executable, but it does not support '-Aaliases'.\n" + install_msg)

    spath_proc = run_command(["clojure", "-Spath"], capture_output=False)
    if spath_proc.returncode != 0:
        raise RuntimeError("`clojure -Spath` failed; please upgrade to Clojure CLI ≥ 1.10.")


class ClojureLSP(SolidLanguageServer):
    """
    Provides a clojure-lsp specific instantiation of the LanguageServer class. Contains various configurations and settings specific to clojure.
    """

    clojure_lsp_releases = "https://github.com/clojure-lsp/clojure-lsp/releases/latest/download"
    runtime_dependencies = RuntimeDependencyCollection(
        [
            RuntimeDependency(
                id="clojure-lsp",
                url=f"{clojure_lsp_releases}/clojure-lsp-native-macos-aarch64.zip",
                platform_id="osx-arm64",
                archive_type="zip",
                binary_name="clojure-lsp",
            ),
            RuntimeDependency(
                id="clojure-lsp",
                url=f"{clojure_lsp_releases}/clojure-lsp-native-macos-amd64.zip",
                platform_id="osx-x64",
                archive_type="zip",
                binary_name="clojure-lsp",
            ),
            RuntimeDependency(
                id="clojure-lsp",
                url=f"{clojure_lsp_releases}/clojure-lsp-native-linux-aarch64.zip",
                platform_id="linux-arm64",
                archive_type="zip",
                binary_name="clojure-lsp",
            ),
            RuntimeDependency(
                id="clojure-lsp",
                url=f"{clojure_lsp_releases}/clojure-lsp-native-linux-amd64.zip",
                platform_id="linux-x64",
                archive_type="zip",
                binary_name="clojure-lsp",
            ),
            RuntimeDependency(
                id="clojure-lsp",
                url=f"{clojure_lsp_releases}/clojure-lsp-native-windows-amd64.zip",
                platform_id="win-x64",
                archive_type="zip",
                binary_name="clojure-lsp.exe",
            ),
        ]
    )

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a ClojureLSP instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "clojure",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self.resolve_main_method_available = threading.Event()
        self.service_ready_event = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """Setup runtime dependencies for clojure-lsp and return the path to the executable."""
            verify_clojure_cli()
            deps = ClojureLSP.runtime_dependencies
            dependency = deps.get_single_dep_for_current_platform()

            clojurelsp_executable_path = deps.binary_path(self._ls_resources_dir)
            if not os.path.exists(clojurelsp_executable_path):
                log.info(
                    f"Downloading and extracting clojure-lsp from {dependency.url} to {self._ls_resources_dir}",
                )
                deps.install(self._ls_resources_dir)
            if not os.path.exists(clojurelsp_executable_path):
                raise FileNotFoundError(f"Download failed? Could not find clojure-lsp executable at {clojurelsp_executable_path}")
            os.chmod(clojurelsp_executable_path, 0o755)
            return clojurelsp_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Returns the init params for clojure-lsp."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        result = {  # type: ignore
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {"documentChanges": True},
                    "symbol": {"symbolKind": {"valueSet": list(range(1, 27))}},
                    "workspaceFolders": True,
                },
                "textDocument": {
                    "synchronization": {"didSave": True},
                    "publishDiagnostics": {"relatedInformation": True, "tagSupport": {"valueSet": [1, 2]}},
                    "definition": {"linkSupport": True},
                    "references": {},
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},  #
                    },
                },
                "general": {"positionEncodings": ["utf-16"]},
            },
            "initializationOptions": {"dependency-scheme": "jar", "text-document-sync-kind": "incremental"},
            "trace": "off",
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(repository_absolute_path)}],
        }
        return cast(InitializeParams, result)

    def _start_server(self) -> None:
        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    self.resolve_main_method_available.set()
            return

        def lang_status_handler(params: dict) -> None:
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def check_experimental_status(params: dict) -> None:
            if params["quiescent"] is True:
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

        log.info("Starting clojure-lsp server process")
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        assert init_response["capabilities"]["textDocumentSync"]["change"] == 2  # type: ignore
        assert "completionProvider" in init_response["capabilities"]
        # Clojure-lsp completion provider capabilities are more flexible than other servers'
        completion_provider = init_response["capabilities"]["completionProvider"]
        assert completion_provider["resolveProvider"] is True
        assert "triggerCharacters" in completion_provider
        self.server.notify.initialized({})
        # after initialize, Clojure-lsp is ready to serve
        self.server_ready.set()
