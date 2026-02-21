"""
Provides TypeScript specific instantiation of the LanguageServer class. Contains various configurations and settings specific to TypeScript.
"""

import logging
import os
import pathlib
import shutil
import threading
from typing import Any, cast

from overrides import override
from sensai.util.logging import LogTime

from solidlsp import ls_types
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

# Platform-specific imports
if os.name != "nt":  # Unix-like systems
    import pwd
else:
    # Dummy pwd module for Windows
    class pwd:  # type: ignore
        @staticmethod
        def getpwuid(uid: Any) -> Any:
            return type("obj", (), {"pw_name": os.environ.get("USERNAME", "unknown")})()


# Conditionally import pwd module (Unix-only)
if not PlatformUtils.get_platform_id().value.startswith("win"):
    pass


def prefer_non_node_modules_definition(definitions: list[ls_types.Location]) -> ls_types.Location:
    """
    Select the preferred definition, preferring source files over type definitions.

    TypeScript language servers often return both type definitions (.d.ts files
    in node_modules) and source definitions. This function prefers:
    1. Files not in node_modules
    2. Falls back to first definition if all are in node_modules

    :param definitions: A non-empty list of definition locations.
    :return: The preferred definition location.
    """
    for d in definitions:
        rel_path = d.get("relativePath", "")
        if rel_path and "node_modules" not in rel_path:
            return d
    return definitions[0]


class TypeScriptLanguageServer(SolidLanguageServer):
    """
    Provides TypeScript specific instantiation of the LanguageServer class. Contains various configurations and settings specific to TypeScript.

    You can pass the following entries in ls_specific_settings["typescript"]:
        - typescript_version: Version of TypeScript to install (default: "5.9.3")
        - typescript_language_server_version: Version of typescript-language-server to install (default: "5.1.3")
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a TypeScriptLanguageServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "typescript",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()
        self._indexing_complete = threading.Event()
        self._active_progress_tokens: set = set()
        self._progress_lock = threading.Lock()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
        ]

    @staticmethod
    def _determine_log_level(line: str) -> int:
        """Classify typescript-language-server stderr output to avoid false-positive errors."""
        return SolidLanguageServer._determine_log_level(line)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Setup runtime dependencies for TypeScript Language Server and return the path to the executable.
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
            assert (
                platform_id in valid_platforms
            ), f"Platform {platform_id} is not supported for multilspy javascript/typescript at the moment"

            # Get version settings from ls_specific_settings or use defaults
            language_specific_config = self._custom_settings
            typescript_version = language_specific_config.get("typescript_version", "5.9.3")
            typescript_language_server_version = language_specific_config.get("typescript_language_server_version", "5.1.3")

            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="typescript",
                        description="typescript package",
                        command=["npm", "install", "--prefix", "./", f"typescript@{typescript_version}"],
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="typescript-language-server",
                        description="typescript-language-server package",
                        command=["npm", "install", "--prefix", "./", f"typescript-language-server@{typescript_language_server_version}"],
                        platform_id="any",
                    ),
                ]
            )

            # Verify both node and npm are installed
            is_node_installed = shutil.which("node") is not None
            assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            is_npm_installed = shutil.which("npm") is not None
            assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

            # Install typescript and typescript-language-server if not already installed or version mismatch
            tsserver_ls_dir = os.path.join(self._ls_resources_dir, "ts-lsp")
            tsserver_executable_path = os.path.join(tsserver_ls_dir, "node_modules", ".bin", "typescript-language-server")

            # Check if installation is needed based on executable AND version
            version_file = os.path.join(tsserver_ls_dir, ".installed_version")
            expected_version = f"{typescript_version}_{typescript_language_server_version}"

            needs_install = False
            if not os.path.exists(tsserver_executable_path):
                log.info(f"Typescript Language Server executable not found at {tsserver_executable_path}.")
                needs_install = True
            elif os.path.exists(version_file):
                with open(version_file) as f:
                    installed_version = f.read().strip()
                if installed_version != expected_version:
                    log.info(
                        f"TypeScript Language Server version mismatch: installed={installed_version}, expected={expected_version}. Reinstalling..."
                    )
                    needs_install = True
            else:
                # No version file exists, assume old installation needs refresh
                log.info("TypeScript Language Server version file not found. Reinstalling to ensure correct version...")
                needs_install = True

            if needs_install:
                log.info("Installing TypeScript Language Server dependencies...")
                with LogTime("Installation of TypeScript language server dependencies", logger=log):
                    deps.install(tsserver_ls_dir)
                # Write version marker file
                with open(version_file, "w") as f:
                    f.write(expected_version)
                log.info("TypeScript language server dependencies installed successfully")

            if not os.path.exists(tsserver_executable_path):
                raise FileNotFoundError(
                    f"typescript-language-server executable not found at {tsserver_executable_path}, something went wrong with the installation."
                )
            return tsserver_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the TypeScript Language Server.
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
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
                "window": {
                    "workDoneProgress": True,
                },
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
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """
        Starts the TypeScript Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(params: dict) -> list:
            return []

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def check_experimental_status(params: dict) -> None:
            """
            Listen for experimental/serverStatus — tsserver signals readiness via quiescent=true
            when all background work (project loading, typechecking) is complete.
            """
            if params.get("quiescent") is True:
                self.server_ready.set()

        def work_done_progress_create(params: dict) -> dict:
            """Handle window/workDoneProgress/create requests from TypeScript LSP."""
            log.debug(f"LSP: window/workDoneProgress/create: {params}")
            return {}

        def progress_handler(params: dict) -> None:
            """Track $/progress notifications to detect when TypeScript LSP indexing completes."""
            token = params.get("token", "")
            value = params.get("value", {})
            kind = value.get("kind")

            if kind == "begin":
                title = value.get("title", "")
                log.info(f"TypeScript LSP progress [{token}]: started - {title}")
                with self._progress_lock:
                    self._active_progress_tokens.add(token)
            elif kind == "report":
                percentage = value.get("percentage")
                message = value.get("message", "")
                if percentage is not None:
                    log.debug(f"TypeScript LSP progress [{token}]: {message} ({percentage}%)")
                elif message:
                    log.debug(f"TypeScript LSP progress [{token}]: {message}")
            elif kind == "end":
                message = value.get("message", "")
                log.info(f"TypeScript LSP progress [{token}]: ended - {message}")
                with self._progress_lock:
                    self._active_progress_tokens.discard(token)
                    if not self._active_progress_tokens:
                        self._indexing_complete.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_notification("$/progress", progress_handler)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        log.info("Starting TypeScript server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info(
            "Sending initialize request from LSP client to LSP server and awaiting response",
        )
        init_response = self.server.send.initialize(initialize_params)

        # TypeScript-specific capability checks
        assert init_response["capabilities"]["textDocumentSync"] == 2
        assert "completionProvider" in init_response["capabilities"]
        assert init_response["capabilities"]["completionProvider"] == {
            "triggerCharacters": [".", '"', "'", "/", "@", "<"],
            "resolveProvider": True,
        }

        self.server.notify.initialized({})

        # Wait for TypeScript server to finish indexing.
        # Primary signal: experimental/serverStatus.quiescent (tsserver-specific)
        # Backup signal: $/progress token completion
        # Note: some versions of typescript-language-server do NOT emit quiescent or
        # $/progress at all; we use a short initial probe (5s) to avoid blocking
        # startup when no signals arrive. Cross-file referencing has its own buffer.
        log.info("Waiting for TypeScript server to become ready...")
        if self.server_ready.wait(timeout=5.0):
            log.info("TypeScript server is ready (quiescent)")
        else:
            # Check if progress tokens are still active (backup signal)
            with self._progress_lock:
                has_active = bool(self._active_progress_tokens)
            if has_active:
                # Progress tokens registered — the LS IS reporting work, wait for it
                log.info("TypeScript LSP indexing in progress, waiting up to 60s more...")
                if self._indexing_complete.wait(timeout=60.0):
                    log.info("TypeScript LSP indexing completed via progress tracking")
                else:
                    log.warning("Timeout waiting for TypeScript LSP indexing (65s total), proceeding anyway")
            else:
                log.info("No TypeScript readiness signal received (5s), proceeding")
            self.server_ready.set()

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """Buffer for cross-file referencing. Applied lazily on the first cross-file
        request (after at least one file is opened in the LS). This gives the TS
        server extra time to finish background analysis of the workspace.
        """
        return 5.0

    @override
    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        return prefer_non_node_modules_definition(definitions)
