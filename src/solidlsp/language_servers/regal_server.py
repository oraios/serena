"""Regal Language Server implementation for Rego policy files."""

import logging
import os
import shutil
import threading

from overrides import override

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PathUtils, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection


class RegalLanguageServer(SolidLanguageServer):
    """
    Provides Rego specific instantiation of the LanguageServer class using Regal.

    Regal is the official linter and language server for Rego (Open Policy Agent's policy language).
    See: https://github.com/StyraInc/regal
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [".regal", ".opa"]

    @classmethod
    def _setup_runtime_dependencies(cls, logger: LanguageServerLogger, solidlsp_settings: SolidLSPSettings) -> str:
        """
        Setup runtime dependencies for Regal language server.

        Downloads and installs Regal if not already present on the system.

        :param logger: Logger instance for logging messages
        :param solidlsp_settings: Settings for solidlsp
        :return: Path to the Regal executable
        """
        # Check if regal is already installed on the system
        system_regal = shutil.which("regal")
        if system_regal:
            logger.log(f"Found system-installed Regal at: {system_regal}", logging.INFO)
            return system_regal

        # If not found, download and install Regal
        platform_id = PlatformUtils.get_platform_id()
        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="Regal",
                    description="Regal language server for macOS (ARM64)",
                    url="https://github.com/StyraInc/regal/releases/download/v0.36.1/regal_Darwin_arm64",
                    platform_id="osx-arm64",
                    archive_type="none",
                    binary_name="regal",
                ),
                RuntimeDependency(
                    id="Regal",
                    description="Regal language server for macOS (x64)",
                    url="https://github.com/StyraInc/regal/releases/download/v0.36.1/regal_Darwin_x86_64",
                    platform_id="osx-x64",
                    archive_type="none",
                    binary_name="regal",
                ),
                RuntimeDependency(
                    id="Regal",
                    description="Regal language server for Linux (ARM64)",
                    url="https://github.com/StyraInc/regal/releases/download/v0.36.1/regal_Linux_arm64",
                    platform_id="linux-arm64",
                    archive_type="none",
                    binary_name="regal",
                ),
                RuntimeDependency(
                    id="Regal",
                    description="Regal language server for Linux (x64)",
                    url="https://github.com/StyraInc/regal/releases/download/v0.36.1/regal_Linux_x86_64",
                    platform_id="linux-x64",
                    archive_type="none",
                    binary_name="regal",
                ),
                RuntimeDependency(
                    id="Regal",
                    description="Regal language server for Windows (x64)",
                    url="https://github.com/StyraInc/regal/releases/download/v0.36.1/regal_Windows_x86_64.exe",
                    platform_id="win-x64",
                    archive_type="none",
                    binary_name="regal.exe",
                ),
            ]
        )
        dependency = deps.get_single_dep_for_current_platform()

        regal_executable_path = deps.binary_path(cls.ls_resources_dir(solidlsp_settings))
        if not os.path.exists(regal_executable_path):
            logger.log(f"Downloading Regal from {dependency.url}", logging.INFO)
            deps.install(logger, cls.ls_resources_dir(solidlsp_settings))

        assert os.path.exists(regal_executable_path), f"Regal executable not found at {regal_executable_path}"

        # Make the executable file executable on Unix-like systems
        if platform_id.value != "win-x64":
            os.chmod(regal_executable_path, 0o755)

        return regal_executable_path

    def __init__(
        self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str, solidlsp_settings: SolidLSPSettings
    ):
        """
        Creates a RegalLanguageServer instance.

        This class is not meant to be instantiated directly. Use LanguageServer.create() instead.

        :param config: Language server configuration
        :param logger: Logger instance
        :param repository_root_path: Path to the repository root
        :param solidlsp_settings: Settings for solidlsp
        """
        regal_executable_path = self._setup_runtime_dependencies(logger, solidlsp_settings)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=f"{regal_executable_path} language-server", cwd=repository_root_path),
            "rego",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Regal Language Server.

        :param repository_absolute_path: Absolute path to the repository
        :return: LSP initialization parameters
        """
        root_uri = PathUtils.path_to_uri(repository_absolute_path)
        return {
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
                    "formatting": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [
                {
                    "name": os.path.basename(repository_absolute_path),
                    "uri": root_uri,
                }
            ],
        }

    def _start_server(self) -> None:
        """Start Regal language server process and wait for initialization."""

        def register_capability_handler(params) -> None:  # type: ignore[no-untyped-def]
            return

        def window_log_message(msg) -> None:  # type: ignore[no-untyped-def]
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def do_nothing(params) -> None:  # type: ignore[no-untyped-def]
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        self.logger.log("Starting Regal language server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # Verify server capabilities
        assert "capabilities" in init_response
        assert "textDocumentSync" in init_response["capabilities"]

        self.server.notify.initialized({})
        self.completions_available.set()

        # Regal server is ready immediately after initialization
        self.server_ready.set()
        self.server_ready.wait()
