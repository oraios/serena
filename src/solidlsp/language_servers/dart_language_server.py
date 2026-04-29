import logging
import os
import pathlib
from collections.abc import Hashable
from typing import cast

from overrides import override

from solidlsp.ls import RawDocumentSymbol, SolidLanguageServer
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from ..ls_config import Language, LanguageServerConfig
from ..lsp_protocol_handler.lsp_types import InitializeParams
from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

DART_ALLOWED_HOSTS = ("storage.googleapis.com",)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_DART_SDK_VERSION = "3.7.1"
INITIAL_DART_SDK_SHA256_BY_PLATFORM = {
    "linux-x64": "2813959e7d9650334015b927cc533f5beadfbf7fa48248beec471f8942a0ee71",
    "win-x64": "f56c03122e17abe5be1429eee0a975fb8ed511b6731ec90c6475992d3dee4ea5",
    "win-arm64": "fada411c6538d0ac24c35d6360767241f1298f64cbc5e88716387d54757a105a",
    "osx-x64": "a2765917b6ae49d1ac119553df9584989f9c441a46e8f18c129ba52489658d2e",
    "osx-arm64": "f57c25163092bac818f8ca6250a0d8b2c56344c6a075a1bd7c60da7ac28b32a4",
}
DEFAULT_DART_SDK_VERSION = "3.7.1"
DEFAULT_DART_SDK_SHA256_BY_PLATFORM = {
    "linux-x64": "2813959e7d9650334015b927cc533f5beadfbf7fa48248beec471f8942a0ee71",
    "win-x64": "f56c03122e17abe5be1429eee0a975fb8ed511b6731ec90c6475992d3dee4ea5",
    "win-arm64": "fada411c6538d0ac24c35d6360767241f1298f64cbc5e88716387d54757a105a",
    "osx-x64": "a2765917b6ae49d1ac119553df9584989f9c441a46e8f18c129ba52489658d2e",
    "osx-arm64": "f57c25163092bac818f8ca6250a0d8b2c56344c6a075a1bd7c60da7ac28b32a4",
}


def _dart_sdk_sha(version: str, platform_key: str) -> str | None:
    if version == INITIAL_DART_SDK_VERSION:
        return INITIAL_DART_SDK_SHA256_BY_PLATFORM[platform_key]
    if version == DEFAULT_DART_SDK_VERSION:
        return DEFAULT_DART_SDK_SHA256_BY_PLATFORM[platform_key]
    return None


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

    @override
    def _document_symbols_cache_fingerprint(self) -> Hashable:
        normalize_symbol_name_version = 1
        return normalize_symbol_name_version

    @override
    def _normalize_symbol_name(self, symbol: RawDocumentSymbol, relative_file_path: str) -> str:
        return symbol["name"].rsplit(".", 1)[-1]

    @classmethod
    def _setup_runtime_dependencies(cls, solidlsp_settings: SolidLSPSettings) -> str:
        dart_settings = solidlsp_settings.get_ls_specific_settings(Language.DART)
        dart_sdk_version = dart_settings.get("dart_sdk_version", DEFAULT_DART_SDK_VERSION)
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for Linux (x64)",
                    url=f"https://storage.googleapis.com/dart-archive/channels/stable/release/{dart_sdk_version}/sdk/dartsdk-linux-x64-release.zip",
                    platform_id="linux-x64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart",
                    sha256=_dart_sdk_sha(dart_sdk_version, "linux-x64"),
                    allowed_hosts=DART_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for Windows (x64)",
                    url=f"https://storage.googleapis.com/dart-archive/channels/stable/release/{dart_sdk_version}/sdk/dartsdk-windows-x64-release.zip",
                    platform_id="win-x64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart.exe",
                    sha256=_dart_sdk_sha(dart_sdk_version, "win-x64"),
                    allowed_hosts=DART_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for Windows (arm64)",
                    url=f"https://storage.googleapis.com/dart-archive/channels/stable/release/{dart_sdk_version}/sdk/dartsdk-windows-arm64-release.zip",
                    platform_id="win-arm64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart.exe",
                    sha256=_dart_sdk_sha(dart_sdk_version, "win-arm64"),
                    allowed_hosts=DART_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for macOS (x64)",
                    url=f"https://storage.googleapis.com/dart-archive/channels/stable/release/{dart_sdk_version}/sdk/dartsdk-macos-x64-release.zip",
                    platform_id="osx-x64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart",
                    sha256=_dart_sdk_sha(dart_sdk_version, "osx-x64"),
                    allowed_hosts=DART_ALLOWED_HOSTS,
                ),
                RuntimeDependency(
                    id="DartLanguageServer",
                    description="Dart Language Server for macOS (arm64)",
                    url=f"https://storage.googleapis.com/dart-archive/channels/stable/release/{dart_sdk_version}/sdk/dartsdk-macos-arm64-release.zip",
                    platform_id="osx-arm64",
                    archive_type="zip",
                    binary_name="dart-sdk/bin/dart",
                    sha256=_dart_sdk_sha(dart_sdk_version, "osx-arm64"),
                    allowed_hosts=DART_ALLOWED_HOSTS,
                ),
            ]
        )

        # legacy unversioned dir reserved for INITIAL; every other version goes into a versioned subdir
        dart_ls_dir = (
            cls.ls_resources_dir(solidlsp_settings)
            if dart_sdk_version == INITIAL_DART_SDK_VERSION
            else os.path.join(cls.ls_resources_dir(solidlsp_settings), f"dart-sdk-{dart_sdk_version}")
        )
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
            "capabilities": {
                "textDocument": {
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True,
                    }
                }
            },
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
