import logging
import os
import pathlib
import stat

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection


class DartLanguageServer(SolidLanguageServer):
    """
    Provides Dart specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Dart.
    """

    def __init__(self, config, logger, repository_root_path, solidlsp_settings: SolidLSPSettings):
        """
        Creates a DartServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        executable_path = self._setup_runtime_dependencies(logger, solidlsp_settings)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=executable_path, cwd=repository_root_path),
            "dart",
            solidlsp_settings,
        )

    @classmethod
    def _setup_runtime_dependencies(cls, logger: "LanguageServerLogger", solidlsp_settings: SolidLSPSettings) -> str:
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for Linux (x64)",
                    url="https://storage.googleapis.com/dart-archive/channels/stable/release/3.7.1/sdk/dartsdk-linux-x64-release.zip",
                    platform_id="linux-x64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart",
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for Windows (x64)",
                    url="https://storage.googleapis.com/dart-archive/channels/stable/release/3.7.1/sdk/dartsdk-windows-x64-release.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart.exe",
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for Windows (arm64)",
                    url="https://storage.googleapis.com/dart-archive/channels/stable/release/3.7.1/sdk/dartsdk-windows-arm64-release.zip",
                    platform_id="win-arm64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart.exe",
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for macOS (x64)",
                    url="https://storage.googleapis.com/dart-archive/channels/stable/release/3.7.1/sdk/dartsdk-macos-x64-release.zip",
                    platform_id="osx-x64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart",
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for macOS (arm64)",
                    url="https://storage.googleapis.com/dart-archive/channels/stable/release/3.7.1/sdk/dartsdk-macos-arm64-release.zip",
                    platform_id="osx-arm64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart",
                ),
            ]
        )

        dart_ls_dir = cls.ls_resources_dir(solidlsp_settings)
        dart_executable_path = deps.binary_path(dart_ls_dir)

        if not os.path.exists(dart_executable_path):
            deps.install(logger, dart_ls_dir)

        assert os.path.exists(dart_executable_path)
        os.chmod(dart_executable_path, stat.S_IEXEC)

        return f"{dart_executable_path} language-server --client-id multilspy.dart --client-version 1.2"

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str):
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

        return initialize_params

    def _start_server(self):
        """
        Start the language server and yield when the server is ready.
        """

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def check_experimental_status(params):
            pass

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        self.logger.log("Starting dart-language-server server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)
        self.logger.log(
            "Sending initialize request to dart-language-server",
            logging.DEBUG,
        )
        init_response = self.server.send_request("initialize", initialize_params)
        self.logger.log(
            f"Received initialize response from dart-language-server: {init_response}",
            logging.INFO,
        )

        self.server.notify.initialized({})
