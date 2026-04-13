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

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

CLOJURE_LSP_VERSION = "2026.02.20-16.08.58"
CLOJURE_LSP_ALLOWED_HOSTS = (
    "github.com",
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
)


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
    Provides a clojure-lsp specific instantiation of the LanguageServer class.

    You can pass the following entries in ``ls_specific_settings["clojure"]``:
        - clojure_lsp_version: Override the pinned clojure-lsp version downloaded
          by Serena (default: the bundled Serena version).
    """

    CLOJURE_LSP_VERSION = CLOJURE_LSP_VERSION
    CLOJURE_LSP_ALLOWED_HOSTS = CLOJURE_LSP_ALLOWED_HOSTS

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        ignored_dirs = [".clj-kondo", ".lsp", ".cpcache"]
        return super().is_ignored_dirname(dirname) or dirname in ignored_dirs

    @classmethod
    def _runtime_dependencies(cls, version: str) -> RuntimeDependencyCollection:
        clojure_lsp_releases = f"https://github.com/clojure-lsp/clojure-lsp/releases/download/{version}"
        default_version = version == cls.CLOJURE_LSP_VERSION
        return RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="clojure-lsp",
                    url=f"{clojure_lsp_releases}/clojure-lsp-native-macos-aarch64.zip",
                    platform_id="osx-arm64",
                    archive_type="zip",
                    binary_name="clojure-lsp",
                    sha256="a14d4db074f665378214e2dc888472e186c228dfa065c777b0534bfda5571669" if default_version else None,
                    allowed_hosts=CLOJURE_LSP_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="clojure-lsp",
                    url=f"{clojure_lsp_releases}/clojure-lsp-native-macos-amd64.zip",
                    platform_id="osx-x64",
                    archive_type="zip",
                    binary_name="clojure-lsp",
                    sha256="5507434c27104ab816e096d3336d8191641de8a65b57d76afb585d07167a3cf2" if default_version else None,
                    allowed_hosts=CLOJURE_LSP_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="clojure-lsp",
                    url=f"{clojure_lsp_releases}/clojure-lsp-native-linux-aarch64.zip",
                    platform_id="linux-arm64",
                    archive_type="zip",
                    binary_name="clojure-lsp",
                    sha256="f8f09fa07dd4b6743b5c57270ccf1ee5cdbc5fca09dbca8b6a3b22705b5da4e1" if default_version else None,
                    allowed_hosts=CLOJURE_LSP_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="clojure-lsp",
                    url=f"{clojure_lsp_releases}/clojure-lsp-native-linux-amd64.zip",
                    platform_id="linux-x64",
                    archive_type="zip",
                    binary_name="clojure-lsp",
                    sha256="52e8bf4fd4cf171df0a3077c8bb5a3bf598d4c621e94b4876dab943a61267309" if default_version else None,
                    allowed_hosts=CLOJURE_LSP_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="clojure-lsp",
                    url=f"{clojure_lsp_releases}/clojure-lsp-native-windows-amd64.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="clojure-lsp.exe",
                    sha256="817b1271288817c954fb9e595278b1f25003827ce31f8785f253dc4ac911041f" if default_version else None,
                    allowed_hosts=CLOJURE_LSP_ALLOWED_HOSTS,
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
            clojure_lsp_version = self._custom_settings.get("clojure_lsp_version", ClojureLSP.CLOJURE_LSP_VERSION)
            deps = ClojureLSP._runtime_dependencies(clojure_lsp_version)
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
