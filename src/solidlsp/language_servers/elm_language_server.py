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
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection


class ElmLanguageServer(SolidLanguageServer):
    """
    Provides Elm specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Elm.
    """

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates an ElmLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        elm_lsp_executable_path = self._setup_runtime_dependencies(logger, config, solidlsp_settings)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=elm_lsp_executable_path, cwd=repository_root_path),
            "elm",
            solidlsp_settings,
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
    def _setup_runtime_dependencies(
        cls, logger: LanguageServerLogger, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> list[str]:
        """
        Setup runtime dependencies for Elm Language Server and return the command to start the server.
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
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for Elm language server at the moment"

        # Check if elm-language-server is already installed globally
        system_elm_ls = shutil.which("elm-language-server")
        if system_elm_ls:
            logger.log(f"Found system-installed elm-language-server at {system_elm_ls}", logging.INFO)
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
            logger.log(f"Elm Language Server executable not found at {elm_ls_executable_path}. Installing...", logging.INFO)
            with LogTime("Installation of Elm language server dependencies", logger=logger.logger):
                deps.install(logger, elm_ls_dir)

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
        return initialize_params

    def _start_server(self):
        """
        Starts the Elm Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting Elm server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # Elm-specific capability checks
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.logger.log("Elm server initialized successfully, waiting for workspace scan...", logging.INFO)

        self.server_ready.set()
        self.completions_available.set()
        self.logger.log("Elm server ready", logging.INFO)

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 1.0
