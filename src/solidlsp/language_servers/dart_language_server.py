import logging
import os
import pathlib
from typing import cast

from solidlsp.ls import SolidLanguageServer
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from ..ls_config import Language, LanguageServerConfig
from ..lsp_protocol_handler.lsp_types import InitializeParams
from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

DART_ALLOWED_HOSTS = ("storage.googleapis.com",)


class DartLanguageServer(SolidLanguageServer):
    """
    Provides Dart specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Dart.

    You can pass the following entries in ``ls_specific_settings["dart"]``:
        - dart_sdk_version: Override the pinned Dart SDK version downloaded by Serena
          (default: the bundled Serena version).
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings) -> None:
        """
        Creates a DartServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        executable_path = self._setup_runtime_dependencies(solidlsp_settings)
        super().__init__(
            config, repository_root_path, ProcessLaunchInfo(cmd=executable_path, cwd=repository_root_path), "dart", solidlsp_settings
        )

    @classmethod
    def _setup_runtime_dependencies(cls, solidlsp_settings: SolidLSPSettings) -> str:
        dart_settings = solidlsp_settings.get_ls_specific_settings(Language.DART)
        dart_sdk_version = dart_settings.get("dart_sdk_version", "3.7.1")
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for Linux (x64)",
                    url=f"https://storage.googleapis.com/dart-archive/channels/stable/release/{dart_sdk_version}/sdk/dartsdk-linux-x64-release.zip",
                    platform_id="linux-x64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart",
                    sha256="2813959e7d9650334015b927cc533f5beadfbf7fa48248beec471f8942a0ee71" if dart_sdk_version == "3.7.1" else None,
                    allowed_hosts=DART_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for Windows (x64)",
                    url=f"https://storage.googleapis.com/dart-archive/channels/stable/release/{dart_sdk_version}/sdk/dartsdk-windows-x64-release.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart.exe",
                    sha256="f56c03122e17abe5be1429eee0a975fb8ed511b6731ec90c6475992d3dee4ea5" if dart_sdk_version == "3.7.1" else None,
                    allowed_hosts=DART_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for Windows (arm64)",
                    url=f"https://storage.googleapis.com/dart-archive/channels/stable/release/{dart_sdk_version}/sdk/dartsdk-windows-arm64-release.zip",
                    platform_id="win-arm64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart.exe",
                    sha256="fada411c6538d0ac24c35d6360767241f1298f64cbc5e88716387d54757a105a" if dart_sdk_version == "3.7.1" else None,
                    allowed_hosts=DART_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for macOS (x64)",
                    url=f"https://storage.googleapis.com/dart-archive/channels/stable/release/{dart_sdk_version}/sdk/dartsdk-macos-x64-release.zip",
                    platform_id="osx-x64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart",
                    sha256="a2765917b6ae49d1ac119553df9584989f9c441a46e8f18c129ba52489658d2e" if dart_sdk_version == "3.7.1" else None,
                    allowed_hosts=DART_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for macOS (arm64)",
                    url=f"https://storage.googleapis.com/dart-archive/channels/stable/release/{dart_sdk_version}/sdk/dartsdk-macos-arm64-release.zip",
                    platform_id="osx-arm64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart",
                    sha256="f57c25163092bac818f8ca6250a0d8b2c56344c6a075a1bd7c60da7ac28b32a4" if dart_sdk_version == "3.7.1" else None,
                    allowed_hosts=DART_ALLOWED_HOSTS,
                ),
            ]
        )

        dart_ls_dir = cls.ls_resources_dir(solidlsp_settings)
        dart_executable_path = deps.binary_path(dart_ls_dir)

        if not os.path.exists(dart_executable_path):
            deps.install(dart_ls_dir)

        assert os.path.exists(dart_executable_path)
        os.chmod(dart_executable_path, 0o755)

        return f"{dart_executable_path} language-server --client-id multilspy.dart --client-version 1.2"

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Dart Language Server.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "capabilities": {},
            "initializationOptions": {
                "onlyAnalyzeProjectsWithOpenFiles": False,
                "closingLabels": False,
                "outline": False,
                "flutterOutline": False,
                "allowOpenUri": False,
            },
            "trace": "verbose",
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": pathlib.Path(repository_absolute_path).as_uri(),
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
        Start the language server and yield when the server is ready.
        """

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def check_experimental_status(params: dict) -> None:
            pass

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        log.info("Starting dart-language-server server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)
        log.debug("Sending initialize request to dart-language-server")
        init_response = self.server.send_request("initialize", initialize_params)  # type: ignore
        log.info(f"Received initialize response from dart-language-server: {init_response}")

        self.server.notify.initialized({})
