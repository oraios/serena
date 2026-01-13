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
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)


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
    def _setup_runtime_dependencies(cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings) -> str:
        """Setup runtime dependencies for marksman and return the command to start the server."""
        deps = cls.runtime_dependencies
        dependency = deps.get_single_dep_for_current_platform()

        marksman_ls_dir = cls.ls_resources_dir(solidlsp_settings)
        marksman_executable_path = deps.binary_path(marksman_ls_dir)
        if not os.path.exists(marksman_executable_path):
            log.info(
                f"Downloading marksman from {dependency.url} to {marksman_ls_dir}",
            )
            deps.install(marksman_ls_dir)
        if not os.path.exists(marksman_executable_path):
            raise FileNotFoundError(f"Download failed? Could not find marksman executable at {marksman_executable_path}")
        os.chmod(marksman_executable_path, 0o755)
        return marksman_executable_path

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a Marksman instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        custom_command = solidlsp_settings.get_ls_specific_settings(self.get_language_enum_instance()).get(SolidLSPSettings.CustomLSSettings.COMMAND_KEY, None)
        if custom_command:
            cmd = custom_command
        else:
            marksman_executable_path = self._setup_runtime_dependencies(config, solidlsp_settings)
            cmd = f"{marksman_executable_path} server"

        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
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
                        "symbolKind": {"valueSet": list(range(1, 27))},  # type: ignore[arg-type]
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},  # type: ignore[list-item]
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

    def _start_server(self) -> None:
        """
        Starts the Marksman Language Server and waits for it to be ready.
        """

        def register_capability_handler(_params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(_params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting marksman server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to marksman server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from marksman server: {init_response}")

        # Verify server capabilities
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # marksman is typically ready immediately after initialization
        log.info("Marksman server initialization complete")
        self.server_ready.set()
        self.completions_available.set()
