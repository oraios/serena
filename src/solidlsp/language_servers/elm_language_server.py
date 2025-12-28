"""
Provides Elm specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Elm.
"""

import logging
import os
import pathlib
import shutil
import threading

from overrides import override
from sensai.util.logging import LogTime

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)


class ElmLanguageServer(SolidLanguageServer):
    """
    Provides Elm specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Elm.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates an ElmLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        elm_lsp_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=elm_lsp_executable_path, cwd=repository_root_path), "elm", solidlsp_settings
        )
        self.server_ready = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "elm-stuff",
            "node_modules",
            "dist",
            "build",
        ]

    @classmethod
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> list[str]:
        """
        Setup runtime dependencies for Elm Language Server and return the command to start the server.
        """
        # Check if elm-language-server is already installed globally
        system_elm_ls = shutil.which("elm-language-server")
        if system_elm_ls:
            log.info(f"Found system-installed elm-language-server at {system_elm_ls}")
            return [system_elm_ls, "--stdio"]

        # Verify node and npm are installed
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="elm-language-server",
                    description="@elm-tooling/elm-language-server package",
                    command=["npm", "install", "--prefix", "./", "@elm-tooling/elm-language-server@2.8.0"],
                    platform_id="any",
                ),
            ]
        )

        # Install elm-language-server if not already installed
        elm_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "elm-lsp")
        elm_ls_executable_path = os.path.join(elm_ls_dir, "node_modules", ".bin", "elm-language-server")
        if not os.path.exists(elm_ls_executable_path):
            log.info(f"Elm Language Server executable not found at {elm_ls_executable_path}. Installing...")
            with LogTime("Installation of Elm language server dependencies", logger=log):
                deps.install(elm_ls_dir)

        if not os.path.exists(elm_ls_executable_path):
            raise FileNotFoundError(
                f"elm-language-server executable not found at {elm_ls_executable_path}, something went wrong with the installation."
            )
        return [elm_ls_executable_path, "--stdio"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Elm Language Server.
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
                    "inlayHint": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "initializationOptions": {
                "elmPath": "elm",
                "elmFormatPath": "elm-format",
                "elmTestPath": "elm-test",
                "skipInstallPackageConfirmation": True,
                "onlyUpdateDiagnosticsOnSave": False,
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
        return initialize_params  # type: ignore[return-value]

    def _start_server(self) -> None:
        """
        Starts the Elm Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Elm server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        # Elm-specific capability checks
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        log.info("Elm server initialized successfully, waiting for workspace scan...")

        self.server_ready.set()
        self.completions_available.set()
        log.info("Elm server ready")

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 1.0
