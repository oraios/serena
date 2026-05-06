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

from .common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command

log = logging.getLogger(__name__)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_TYPESCRIPT_VERSION = "5.9.3"
DEFAULT_TYPESCRIPT_VERSION = "5.9.3"
INITIAL_TYPESCRIPT_LANGUAGE_SERVER_VERSION = "5.1.3"
DEFAULT_TYPESCRIPT_LANGUAGE_SERVER_VERSION = "5.1.3"

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

    @classmethod
    def supports_implementation_request(cls) -> bool:
        return True

    # Safety timeout for $/progress-based indexing wait. Normally the event fires
    # well within this window; the timeout is only hit if the server never sends progress.
    INDEXING_PROGRESS_TIMEOUT = 15.0 if os.name == "nt" else 10.0

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

        # tracking asynchronous diagnostics publication
        self._published_diagnostics_timeout = 5.0

        # tracking project indexing progress
        self._progress_lock = threading.Lock()
        self._active_progress_tokens: set[str] = set()
        self._indexing_complete = threading.Event()
        self._indexing_complete.set()  # Initially set (no active work)

    def wait_for_indexing(self, timeout: float) -> bool:
        """Block until all $/progress tokens complete.

        :param timeout: Maximum seconds to wait.
        :return: True if indexing completed, False on timeout.
        """
        return self._indexing_complete.wait(timeout=timeout)

    def expect_indexing(self) -> None:
        """Signal that new files are about to be opened and async indexing should be awaited.

        Clears the internal indexing-complete event so that a subsequent
        :meth:`wait_for_indexing` call blocks until all $/progress tokens
        complete (or the timeout expires).
        """
        self._indexing_complete.clear()

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
            assert platform_id in valid_platforms, (
                f"Platform {platform_id} is not supported for multilspy javascript/typescript at the moment"
            )

            # Get version settings from ls_specific_settings or use defaults
            language_specific_config = self._custom_settings
            typescript_version = language_specific_config.get("typescript_version", DEFAULT_TYPESCRIPT_VERSION)
            typescript_language_server_version = language_specific_config.get(
                "typescript_language_server_version", DEFAULT_TYPESCRIPT_LANGUAGE_SERVER_VERSION
            )
            npm_registry = language_specific_config.get("npm_registry")

            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="typescript",
                        description="typescript package",
                        command=build_npm_install_command("typescript", typescript_version, npm_registry),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="typescript-language-server",
                        description="typescript-language-server package",
                        command=build_npm_install_command("typescript-language-server", typescript_language_server_version, npm_registry),
                        platform_id="any",
                    ),
                ]
            )

            # Verify both node and npm are installed
            is_node_installed = shutil.which("node") is not None
            assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
            is_npm_installed = shutil.which("npm") is not None
            assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

            # legacy unversioned dir reserved for INITIAL pair; any other version combination goes into a versioned subdir
            is_initial = (
                typescript_version == INITIAL_TYPESCRIPT_VERSION
                and typescript_language_server_version == INITIAL_TYPESCRIPT_LANGUAGE_SERVER_VERSION
            )
            ls_dirname = "ts-lsp" if is_initial else f"ts-lsp-{typescript_version}-{typescript_language_server_version}"
            tsserver_ls_dir = os.path.join(self._ls_resources_dir, ls_dirname)
            tsserver_executable_path = os.path.join(tsserver_ls_dir, "node_modules", ".bin", "typescript-language-server")

            if not os.path.exists(tsserver_executable_path):
                log.info(f"Typescript Language Server executable not found at {tsserver_executable_path}. Installing...")
                with LogTime("Installation of TypeScript language server dependencies", logger=log):
                    deps.install(tsserver_ls_dir)
                log.info("TypeScript language server dependencies installed successfully")

            if not os.path.exists(tsserver_executable_path):
                raise FileNotFoundError(
                    f"typescript-language-server executable not found at {tsserver_executable_path}, something went wrong with the installation."
                )
            return tsserver_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        # JSX is parsed as TS without this, which silently truncates symbol
        # ranges at the first multi-line JSX expression.
        if relative_file_path.endswith(".tsx"):
            return "typescriptreact"
        if relative_file_path.endswith(".jsx"):
            return "javascriptreact"
        return self.language_id

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
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "configuration": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
                "window": {
                    "workDoneProgress": True,  # Enables $/progress notifications for project loading
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": self._build_workspace_folders_param(repository_absolute_path),
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
        ```
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    # TypeScript doesn't have a direct equivalent to resolve_main_method
                    # You might want to set a different flag or remove this line
                    # self.resolve_main_method_available.set()
            return

        def execute_client_command_handler(params: dict) -> list:
            return []

        def configuration_handler(params: dict) -> list:
            items = params.get("items", [])
            return [{} for _ in items]

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def handle_typescript_version(params: dict) -> None:
            """
            The $/typescriptVersion notification is sent by typescript-language-server
            once tsserver has loaded and reported its version. This is a reliable
            signal that tsserver is running and responsive.
            """
            log.info(f"TypeScript server version notification received: {params}")
            self.server_ready.set()

        def work_done_progress_create(params: dict) -> dict:
            """Handle window/workDoneProgress/create: the server is about to report async progress.

            Clear the indexing-complete event so callers waiting on it will block until
            all progress tokens finish. This is sent by typescript-language-server when
            tsserver starts processing files (e.g. "Initializing JS/TS language features...").
            """
            token = str(params.get("token", ""))
            log.debug(f"TypeScript LSP workDoneProgress/create: token={token!r}")
            with self._progress_lock:
                self._active_progress_tokens.add(token)
                self._indexing_complete.clear()
            return {}

        def progress_handler(params: dict) -> None:
            """Track $/progress begin/end to detect when all async work finishes.

            typescript-language-server sends $/progress for project loading operations
            like "Initializing JS/TS language features...". When all progress tokens
            complete (kind='end'), _indexing_complete is set.
            """
            token = str(params.get("token", ""))
            value = params.get("value", {})
            kind = value.get("kind")
            if kind == "begin":
                title = value.get("title", "")
                log.info(f"TypeScript LSP progress [{token}]: started - {title}")
                with self._progress_lock:
                    self._active_progress_tokens.add(token)
                    self._indexing_complete.clear()
            elif kind == "report":
                pct = value.get("percentage")
                msg = value.get("message", "")
                pct_str = f" ({pct}%)" if pct is not None else ""
                log.debug(f"TypeScript LSP progress [{token}]: {msg}{pct_str}")
            elif kind == "end":
                msg = value.get("message", "")
                log.info(f"TypeScript LSP progress [{token}]: ended - {msg}")
                with self._progress_lock:
                    self._active_progress_tokens.discard(token)
                    if not self._active_progress_tokens:
                        self._indexing_complete.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_notification("$/progress", progress_handler)
        self.server.on_notification("$/typescriptVersion", handle_typescript_version)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

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
        if self.server_ready.wait(timeout=10.0):
            log.info("TypeScript server is ready")
        else:
            log.info("Timeout waiting for TypeScript server to become ready, proceeding anyway")
            # Fallback: assume server is ready after timeout
            self.server_ready.set()

        # Wait for any async project loading to complete.
        # typescript-language-server may send $/progress for "Initializing JS/TS
        # language features…" after initialized. If no progress is sent,
        # _indexing_complete stays SET and wait() returns immediately.
        log.info("Waiting for TypeScript project indexing to complete (if async)...")
        if self.wait_for_indexing(timeout=self.INDEXING_PROGRESS_TIMEOUT):
            log.info("TypeScript project indexing complete")
        else:
            log.warning(
                "TypeScript project indexing did not complete within %.0fs; proceeding anyway",
                self.INDEXING_PROGRESS_TIMEOUT,
            )

        self._activate_additional_workspaces()

    @override
    def _find_representative_source_file(self, directory: str) -> str | None:
        """Find a TypeScript file suitable for triggering project loading.

        Prefers a file adjacent to tsconfig.json (indicating the project root),
        then falls back to the first .ts/.tsx file found.
        """
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not self.is_ignored_dirname(d)]
            if "tsconfig.json" in files:
                for f in files:
                    if f.endswith((".ts", ".tsx")) and not f.endswith(".d.ts"):
                        return os.path.join(root, f)
                src_dir = os.path.join(root, "src")
                if os.path.isdir(src_dir):
                    for f in os.listdir(src_dir):
                        if f.endswith((".ts", ".tsx")) and not f.endswith(".d.ts"):
                            return os.path.join(src_dir, f)

        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not self.is_ignored_dirname(d)]
            for f in files:
                if f.endswith((".ts", ".tsx")) and not f.endswith(".d.ts"):
                    return os.path.join(root, f)
        return None

    @override
    def _signal_expect_indexing(self) -> None:
        self.expect_indexing()

    @override
    def _wait_for_additional_workspace_indexing(self) -> None:
        if self.wait_for_indexing(timeout=self.INDEXING_PROGRESS_TIMEOUT):
            log.info("Additional workspace indexing complete")
        else:
            log.warning("Additional workspace indexing did not complete within timeout; proceeding anyway")

    @override
    def _get_published_diagnostics_uri(self, request_uri: str) -> str:
        if os.name != "nt" or not request_uri.startswith("file:///"):
            return request_uri

        path_part = request_uri[len("file:///") :]
        if len(path_part) >= 2 and path_part[0].isalpha() and path_part[1] == ":":
            return f"file:///{path_part[0].lower()}%3A{path_part[2:]}"
        return request_uri

    @override
    def _get_published_diagnostics_wait_timeout(self, pull_diagnostics_failed: bool) -> float:
        return self._published_diagnostics_timeout

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 2

    @override
    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        return prefer_non_node_modules_definition(definitions)
