"""
Provides Markdown specific instantiation of the LanguageServer class using marksman.
Contains various configurations and settings specific to Markdown.
"""

import logging
import os
import pathlib
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection


class Marksman(SolidLanguageServer):
    """
    Provides Markdown specific instantiation of the LanguageServer class using marksman.
    """

    marksman_releases = "https://github.com/artempyanykh/marksman/releases/download/2024-12-18"
    runtime_dependencies = RuntimeDependencyCollection(
        [
            RuntimeDependency(
                id="marksman",
                url=f"{marksman_releases}/marksman-linux-x64",
                platform_id="linux-x64",
                archive_type="binary",
                binary_name="marksman",
            ),
            RuntimeDependency(
                id="marksman",
                url=f"{marksman_releases}/marksman-linux-arm64",
                platform_id="linux-arm64",
                archive_type="binary",
                binary_name="marksman",
            ),
            RuntimeDependency(
                id="marksman",
                url=f"{marksman_releases}/marksman-macos",
                platform_id="osx-x64",
                archive_type="binary",
                binary_name="marksman",
            ),
            RuntimeDependency(
                id="marksman",
                url=f"{marksman_releases}/marksman-macos",
                platform_id="osx-arm64",
                archive_type="binary",
                binary_name="marksman",
            ),
            RuntimeDependency(
                id="marksman",
                url=f"{marksman_releases}/marksman.exe",
                platform_id="win-x64",
                archive_type="binary",
                binary_name="marksman.exe",
            ),
        ]
    )

    @classmethod
    def _setup_runtime_dependencies(
        cls, logger: LanguageServerLogger, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> str:
        """Setup runtime dependencies for marksman and return the command to start the server."""
        deps = cls.runtime_dependencies
        dependency = deps.get_single_dep_for_current_platform()

        marksman_ls_dir = cls.ls_resources_dir(solidlsp_settings)
        marksman_executable_path = deps.binary_path(marksman_ls_dir)
        if not os.path.exists(marksman_executable_path):
            logger.log(
                f"Downloading marksman from {dependency.url} to {marksman_ls_dir}",
                logging.INFO,
            )
            deps.install(logger, marksman_ls_dir)
        if not os.path.exists(marksman_executable_path):
            raise FileNotFoundError(f"Download failed? Could not find marksman executable at {marksman_executable_path}")
        os.chmod(marksman_executable_path, 0o755)
        return marksman_executable_path

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a Marksman instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        marksman_executable_path = self._setup_runtime_dependencies(logger, config, solidlsp_settings)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=f"{marksman_executable_path} server", cwd=repository_root_path),
            "markdown",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in ["node_modules", ".obsidian", ".vitepress", ".vuepress"]

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Marksman Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params: InitializeParams = {  # type: ignore
            "processId": os.getpid(),
            "locale": "en",
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
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
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
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
        Starts the Marksman Language Server and waits for it to be ready.
        """

        def register_capability_handler(_params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(_params):
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting marksman server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to marksman server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)
        self.logger.log(f"Received initialize response from marksman server: {init_response}", logging.DEBUG)

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # marksman is typically ready immediately after initialization
        self.logger.log("Marksman server initialization complete", logging.INFO)
        self.server_ready.set()
        self.completions_available.set()
