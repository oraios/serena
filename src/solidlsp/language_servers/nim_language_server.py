import logging
import os
import pathlib
from typing import cast

from solidlsp.ls import SolidLanguageServer
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from ..ls_config import LanguageServerConfig
from ..lsp_protocol_handler.lsp_types import InitializeParams
from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)


class NimLanguageServer(SolidLanguageServer):
    """
    Provides Nim specific instantiation of the LanguageServer class.
    Contains various configurations and settings specific to Nim.

    Uses nimlangserver from https://github.com/nim-lang/langserver
    """

    NIMLANGSERVER_VERSION = "1.12.0"

    def is_ignored_dirname(self, dirname: str) -> bool:
        nim_ignored_dirs = {"nimcache", "nimblecache", "htmldocs", "nimbledeps"}
        return dirname in nim_ignored_dirs or super().is_ignored_dirname(dirname)

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings) -> None:
        """
        Creates a NimLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        executable_path = self._setup_runtime_dependencies(solidlsp_settings)
        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=executable_path, cwd=repository_root_path), "nim", solidlsp_settings
        )

    @classmethod
    def _setup_runtime_dependencies(cls, solidlsp_settings: SolidLSPSettings) -> str:
        v = cls.NIMLANGSERVER_VERSION
        base_url = f"https://github.com/nim-lang/langserver/releases/download/v{v}"
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="NimLanguageServer",
                    description="Nim Language Server for Linux (x64)",
                    url=f"{base_url}/nimlangserver-linux-amd64.tar.gz",
                    platform_id="linux-x64",
                    archive_type="tar.gz",
                    binary_name="nimlangserver",
                ),
                RuntimeDependency(
                    id="NimLanguageServer",
                    description="Nim Language Server for Linux (arm64)",
                    url=f"{base_url}/nimlangserver-linux-arm64.tar.gz",
                    platform_id="linux-arm64",
                    archive_type="tar.gz",
                    binary_name="nimlangserver",
                ),
                RuntimeDependency(
                    id="NimLanguageServer",
                    description="Nim Language Server for macOS (x64)",
                    url=f"{base_url}/nimlangserver-macos-amd64.zip",
                    platform_id="osx-x64",
                    archive_type="zip",
                    binary_name="nimlangserver",
                ),
                RuntimeDependency(
                    id="NimLanguageServer",
                    description="Nim Language Server for macOS (arm64)",
                    url=f"{base_url}/nimlangserver-macos-arm64.zip",
                    platform_id="osx-arm64",
                    archive_type="zip",
                    binary_name="nimlangserver",
                ),
                RuntimeDependency(
                    id="NimLanguageServer",
                    description="Nim Language Server for Windows (x64)",
                    url=f"{base_url}/nimlangserver-windows-amd64.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="nimlangserver.exe",
                ),
            ]
        )

        nim_ls_dir = cls.ls_resources_dir(solidlsp_settings)
        executable_path = deps.binary_path(nim_ls_dir)

        if not os.path.exists(executable_path):
            deps.install(nim_ls_dir)

        assert os.path.exists(executable_path)
        os.chmod(executable_path, 0o755)

        return executable_path

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Nim Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "capabilities": {},
            "initializationOptions": {},
            "trace": "verbose",
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

        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """
        Start the Nim language server and yield when the server is ready.
        """

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting nimlangserver server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)
        log.debug("Sending initialize request to nimlangserver")
        init_response = self.server.send_request("initialize", initialize_params)  # type: ignore
        log.info(f"Received initialize response from nimlangserver: {init_response}")

        self.server.notify.initialized({})
