"""
Svelte Language Server with comprehensive TypeScript support.

This implementation provides full support for mixed Svelte/TypeScript projects using:
- Svelte Language Server for .svelte files and embedded TypeScript
- TypeScript Language Server for standalone .ts/.js files
- Intelligent routing between language servers based on file type
- Symbol tree merging for unified project analysis
- Proper lifecycle management of both language servers
"""

import logging
import os
import pathlib
import shutil
import threading
from time import sleep

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.ls_utils import PlatformId, PlatformUtils
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo

from .common import RuntimeDependency, RuntimeDependencyCollection


class SvelteLanguageServer(SolidLanguageServer):
    """
    Svelte Language Server with dual-language server architecture.

    Provides comprehensive support for Svelte projects by managing:
    - Svelte Language Server for .svelte files with embedded TypeScript
    - TypeScript Language Server for standalone .ts/.js/.tsx/.jsx files
    - Intelligent file routing based on extensions
    - Symbol tree merging for unified project analysis
    - Proper initialization and cleanup of both language servers
    """

    def __init__(self, config: LanguageServerConfig, logger: LanguageServerLogger, repository_root_path: str):
        """Initialize Svelte language server with dual-language server support."""
        svelte_lsp_executable_path = self._setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=svelte_lsp_executable_path, cwd=repository_root_path),
            "svelte",
        )

        # Initialize TypeScript language server for standalone .ts/.js file support
        self._ts_server: SolidLanguageServer | None = None
        self._ts_server_started = False
        self.server_ready = threading.Event()
        self.initialize_searcher_command_available = threading.Event()

    def _get_ts_server(self) -> SolidLanguageServer | None:
        """Lazy initialization of TypeScript language server for .ts files."""
        if self._ts_server is None:
            try:
                ts_config = LanguageServerConfig(Language.TYPESCRIPT)
                self._ts_server = SolidLanguageServer.create(ts_config, self.logger, self.repository_root_path)
                self.logger.log("Created TypeScript LS for Svelte project support", logging.INFO)
            except Exception as e:
                self.logger.log(f"TypeScript LS creation failed, using Svelte LS only: {e}", logging.INFO)
                self._ts_server = None

        # Start the TypeScript server if not already started
        if self._ts_server is not None and not self._ts_server_started:
            try:
                self._ts_server.start()
                self._ts_server_started = True
                self.logger.log("Started TypeScript LS for Svelte project support", logging.INFO)
            except Exception as e:
                self.logger.log(f"TypeScript LS startup failed: {e}", logging.WARNING)
                self._ts_server = None
                self._ts_server_started = False

        return self._ts_server

    def _should_use_typescript_ls(self, file_path: str) -> bool:
        """Determine if TypeScript LS should handle this file."""
        return (
            file_path.endswith((".ts", ".tsx", ".js", ".jsx"))
            and not file_path.endswith(".svelte.ts")
            and self._get_ts_server() is not None
            and self._ts_server_started
        )

    @override
    def request_document_symbols(
        self, relative_file_path: str, include_body: bool = False
    ) -> tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]:
        """Document symbol requests with intelligent language server routing."""
        if self._should_use_typescript_ls(relative_file_path):
            try:
                return self._get_ts_server().request_document_symbols(relative_file_path, include_body)
            except Exception as e:
                self.logger.log(f"TypeScript LS failed for {relative_file_path}: {e}", logging.WARNING)

        # Use Svelte LS for .svelte files and fallback
        return super().request_document_symbols(relative_file_path, include_body)

    @override
    def request_full_symbol_tree(
        self, within_relative_path: str | None = None, include_body: bool = False
    ) -> list[ls_types.UnifiedSymbolInformation]:
        """Symbol tree with merged results from both Svelte and TypeScript language servers."""
        # Get symbols from Svelte LS
        svelte_symbols = super().request_full_symbol_tree(within_relative_path, include_body)

        # Merge with TypeScript symbols if available
        if self._get_ts_server():
            try:
                # Get TypeScript symbols for .ts files
                ts_symbols = self._get_ts_server().request_full_symbol_tree(within_relative_path, include_body)
                # Merge symbols from both sources, avoiding duplicates
                merged_symbols = self._merge_symbol_sources(svelte_symbols, ts_symbols)
                return merged_symbols
            except Exception as e:
                self.logger.log(f"Failed to merge TypeScript symbols: {e}", logging.WARNING)

        return svelte_symbols

    def _merge_symbol_sources(
        self, svelte_symbols: list[ls_types.UnifiedSymbolInformation], ts_symbols: list[ls_types.UnifiedSymbolInformation]
    ) -> list[ls_types.UnifiedSymbolInformation]:
        """Merge symbols from different sources, avoiding duplicates."""
        merged = list(svelte_symbols)

        for ts_symbol in ts_symbols:
            # Only add TypeScript symbols that aren't already covered by Svelte LS
            if self._is_unique_typescript_symbol(ts_symbol, merged):
                merged.append(ts_symbol)

        return merged

    def _is_unique_typescript_symbol(
        self, ts_symbol: ls_types.UnifiedSymbolInformation, existing_symbols: list[ls_types.UnifiedSymbolInformation]
    ) -> bool:
        """Check if TypeScript symbol adds unique value."""
        ts_path = ts_symbol.get("location", {}).get("relativePath", "")
        ts_name = ts_symbol.get("name", "")

        # Skip if it's not a .ts/.js file (Svelte LS should handle .svelte)
        if not ts_path.endswith((".ts", ".tsx", ".js", ".jsx")):
            return False

        # Check for duplicates
        for existing in existing_symbols:
            existing_path = existing.get("location", {}).get("relativePath", "")
            existing_name = existing.get("name", "")

            if ts_name == existing_name and ts_path == existing_path:
                return False

        return True

    @override
    def request_references(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        """Reference finding with intelligent language server routing."""
        if self._should_use_typescript_ls(relative_file_path):
            try:
                return self._get_ts_server().request_references(relative_file_path, line, column)
            except Exception as e:
                self.logger.log(f"TypeScript LS references failed: {e}", logging.WARNING)

        # Use Svelte LS
        return super().request_references(relative_file_path, line, column)

    @override
    def request_definition(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        """Definition finding with intelligent language server routing."""
        if self._should_use_typescript_ls(relative_file_path):
            try:
                return self._get_ts_server().request_definition(relative_file_path, line, column)
            except Exception as e:
                self.logger.log(f"TypeScript LS definition failed: {e}", logging.WARNING)

        # Use Svelte LS
        return super().request_definition(relative_file_path, line, column)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            ".svelte-kit",
            "build",
            "dist",
            "coverage",
            ".vercel",
            ".netlify",
        ]

    @classmethod
    def _setup_runtime_dependencies(cls, logger: LanguageServerLogger, config: LanguageServerConfig) -> str:
        """
        Setup runtime dependencies for Svelte Language Server and return the command to start the server.
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
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for Svelte language server at the moment"

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="svelte-language-server",
                    description="svelte-language-server package",
                    command="npm install --prefix ./ svelte-language-server@0.17.16",
                    platform_id="any",
                ),
            ]
        )

        # Verify both node and npm are installed
        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        # First check if svelte-language-server is available globally
        global_svelteserver = shutil.which("svelteserver")
        if global_svelteserver:
            logger.log("Found global svelte-language-server installation", logging.INFO)
            return f"{global_svelteserver} --stdio"

        # Install svelte-language-server if not already installed
        svelte_ls_dir = os.path.join(cls.ls_resources_dir(), "svelte-lsp")
        # Try multiple possible executable paths
        possible_paths = [
            os.path.join(svelte_ls_dir, "node_modules", ".bin", "svelteserver"),
            os.path.join(svelte_ls_dir, "node_modules", "svelte-language-server", "bin", "server.js"),
        ]

        svelte_executable_path = None
        for path in possible_paths:
            if os.path.exists(path):
                svelte_executable_path = path
                break

        if svelte_executable_path is None:
            logger.log("Svelte Language Server executable not found. Installing...", logging.INFO)
            deps.install(logger, svelte_ls_dir)

            # Check again after installation
            for path in possible_paths:
                if os.path.exists(path):
                    svelte_executable_path = path
                    break

        if svelte_executable_path is None:
            raise FileNotFoundError(
                f"svelte-language-server executable not found at any of: {possible_paths}, something went wrong with the installation."
            )

        # If it's the server.js file, we need to run it with node
        if svelte_executable_path.endswith("server.js"):
            return f"node {svelte_executable_path} --stdio"
        else:
            return f"{svelte_executable_path} --stdio"

    def stop(self) -> None:
        """Stop both Svelte and TypeScript language servers."""
        try:
            if self._ts_server is not None and self._ts_server_started:
                self._ts_server.stop()
                self._ts_server_started = False
                self.logger.log("Stopped TypeScript LS", logging.INFO)
        except Exception as e:
            self.logger.log(f"Error stopping TypeScript LS: {e}", logging.WARNING)

        super().stop()

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Svelte Language Server.
        Updated for Svelte 5 and TypeScript support.
        """
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "change": 2},
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True,
                        },
                    },
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "codeAction": {"dynamicRegistration": True},
                    "formatting": {"dynamicRegistration": True},
                    "rangeFormatting": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "versionSupport": False,
                        "tagSupport": {"valueSet": [1, 2]},
                        "codeDescriptionSupport": True,
                        "dataSupport": True,
                    },
                },
                "workspace": {
                    "workspaceFolders": True,
                    "symbol": {"dynamicRegistration": True},
                    "configuration": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "executeCommand": {"dynamicRegistration": True},
                },
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
            "initializationOptions": {
                "configuration": {
                    "svelte": {
                        "plugin": {
                            "svelte": {"compilerWarnings": {}, "diagnostics": {"enable": True}},
                            "typescript": {"enable": True},
                            "css": {"enable": True},
                            "html": {"enable": True},
                        }
                    }
                }
            },
        }
        return initialize_params

    def _start_server(self) -> None:
        """
        Starts the Svelte Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        """

        def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
            return

        def execute_client_command_handler(params):
            return []

        def do_nothing(params):
            return

        def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        def check_server_ready(params):
            """
            Listen for server status notifications to determine when ready
            """
            if params.get("type") == "ready" or params.get("quiescent") == True:
                self.server_ready.set()
                self.completions_available.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_server_ready)

        self.logger.log("Starting Svelte server process", logging.INFO)
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        self.logger.log(
            "Sending initialize request from LSP client to LSP server and awaiting response",
            logging.INFO,
        )
        init_response = self.server.send.initialize(initialize_params)

        # Svelte-specific capability checks
        capabilities = init_response["capabilities"]
        assert "textDocumentSync" in capabilities
        assert "completionProvider" in capabilities or "completion" in capabilities

        self.server.notify.initialized({})
        if self.server_ready.wait(timeout=2.0):
            self.logger.log("Svelte server is ready", logging.INFO)
        else:
            self.logger.log("Timeout waiting for Svelte server to become ready, proceeding anyway", logging.INFO)
            # Fallback: assume server is ready after timeout
            self.server_ready.set()
        self.completions_available.set()

    @override
    def _send_references_request(self, relative_file_path: str, line: int, column: int) -> list[ls_types.Location]:
        # Similar to TypeScript, may need a small delay for cross-file references
        sleep(0.5)
        return super()._send_references_request(relative_file_path, line, column)
