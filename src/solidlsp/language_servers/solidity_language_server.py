"""
Provides Solidity-specific instantiation of the LanguageServer class using
the Nomic Foundation Solidity Language Server (@nomicfoundation/solidity-language-server).
"""

import glob
import logging
import os
import pathlib
import platform
import shutil
import threading
from time import sleep
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, LSPConstants, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)

# Version pinning convention (see eclipse_jdtls.py for the full spec):
#   INITIAL_* — frozen forever; legacy unversioned install dir is reserved for it.
#   DEFAULT_* — bumped on upgrades; goes into a versioned subdir.
INITIAL_SOLIDITY_LANGUAGE_SERVER_VERSION = "0.8.4"
DEFAULT_SOLIDITY_LANGUAGE_SERVER_VERSION = "0.8.4"
INITIAL_FORGE_VERSION = "1.5.1"
DEFAULT_FORGE_VERSION = "1.5.1"


class SolidityLanguageServer(SolidLanguageServer):
    """
    Provides Solidity-specific instantiation of the LanguageServer class using
    the Nomic Foundation Solidity Language Server (@nomicfoundation/solidity-language-server).
    Supports go-to-definition, find references, document symbols, hover, and diagnostics.
    Requires Node.js and npm to be installed.
    """

    @staticmethod
    def _determine_log_level(line: str) -> int:
        """Suppress known non-critical stderr output from the Solidity language server."""
        line_lower = line.lower()
        if any(
            [
                "telemetry" in line_lower,
                "could not find" in line_lower and "hardhat" in line_lower,
                "no workspaceroot" in line_lower,
            ]
        ):
            return logging.DEBUG
        return SolidLanguageServer._determine_log_level(line)

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a SolidityLanguageServer instance. Not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            repository_root_path,
            None,
            "solidity",
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Install @nomicfoundation/solidity-language-server via npm and return the
            path to the solidity-language-server executable.
            """
            is_node_installed = shutil.which("node") is not None
            assert is_node_installed, "node is not installed or isn't in PATH. Please install Node.js and try again."
            is_npm_installed = shutil.which("npm") is not None
            assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."
            solidity_language_server_version = self._custom_settings.get(
                "solidity_language_server_version", DEFAULT_SOLIDITY_LANGUAGE_SERVER_VERSION
            )
            forge_version = self._custom_settings.get("forge_version", DEFAULT_FORGE_VERSION)
            npm_registry = self._custom_settings.get("npm_registry")

            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="solidity-language-server",
                        description="Nomic Foundation Solidity Language Server",
                        command=build_npm_install_command(
                            "@nomicfoundation/solidity-language-server",
                            solidity_language_server_version,
                            npm_registry,
                        ),
                        platform_id="any",
                    ),
                    RuntimeDependency(
                        id="forge",
                        description="Foundry forge CLI",
                        # the @foundry-rs/forge meta-package's postinstall uses POSIX env-var
                        # syntax that fails on Windows cmd.exe, so we install the platform-specific
                        # subpackage directly to bypass it
                        command=build_npm_install_command(self._get_forge_npm_package(), forge_version, npm_registry),
                        platform_id="any",
                    ),
                ]
            )

            solidity_ls_dir = self._resolve_solidity_ls_dir(solidity_language_server_version, forge_version)
            managed_bin_dir = os.path.join(solidity_ls_dir, "node_modules", ".bin")
            solidity_executable_path = os.path.join(managed_bin_dir, "nomicfoundation-solidity-language-server")
            forge_executable_path = os.path.join(managed_bin_dir, "forge")

            if os.name == "nt":
                solidity_executable_path += ".cmd"
                forge_executable_path += ".cmd"

            if not os.path.exists(solidity_executable_path) or not os.path.exists(forge_executable_path):
                log.info("Solidity Language Server dependencies missing. Installing...")
                deps.install(solidity_ls_dir)
                log.info("Solidity language server dependencies installed successfully.")

            if not os.path.exists(solidity_executable_path):
                raise FileNotFoundError(
                    f"nomicfoundation-solidity-language-server executable not found at {solidity_executable_path}. "
                    "Something went wrong with the installation."
                )

            return solidity_executable_path

        @staticmethod
        def _get_forge_npm_package() -> str:
            """
            Returns the platform-specific @foundry-rs forge npm subpackage name. Installing
            the meta-package fails on Windows due to a POSIX-only postinstall script.
            """
            machine = platform.machine().lower()
            if machine in ("x86_64", "amd64"):
                arch = "amd64"
            elif machine in ("arm64", "aarch64"):
                arch = "arm64"
            else:
                raise RuntimeError(f"Unsupported architecture for foundry forge: {machine}")

            if os.name == "nt":
                if arch != "amd64":
                    raise RuntimeError(f"foundry forge does not publish a Windows {arch} npm package")
                return "@foundry-rs/forge-win32-amd64"
            if platform.system() == "Darwin":
                return f"@foundry-rs/forge-darwin-{arch}"
            return f"@foundry-rs/forge-linux-{arch}"

        def create_launch_command_env(self) -> dict[str, str]:
            solidity_language_server_version = self._custom_settings.get(
                "solidity_language_server_version", DEFAULT_SOLIDITY_LANGUAGE_SERVER_VERSION
            )
            forge_version = self._custom_settings.get("forge_version", DEFAULT_FORGE_VERSION)
            solidity_ls_dir = self._resolve_solidity_ls_dir(solidity_language_server_version, forge_version)
            managed_bin_dir = os.path.join(solidity_ls_dir, "node_modules", ".bin")
            return {"PATH": managed_bin_dir + os.pathsep + os.environ.get("PATH", "")}

        def _resolve_solidity_ls_dir(self, solidity_language_server_version: str, forge_version: str) -> str:
            # legacy unversioned dir reserved for INITIAL pair; any other combination goes into a versioned subdir
            is_initial = (
                solidity_language_server_version == INITIAL_SOLIDITY_LANGUAGE_SERVER_VERSION and forge_version == INITIAL_FORGE_VERSION
            )
            ls_dirname = "solidity-lsp" if is_initial else f"solidity-lsp-{solidity_language_server_version}-{forge_version}"
            return os.path.join(self._ls_resources_dir, ls_dirname)

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--stdio"]

    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in {"artifacts", "cache", "typechain-types"}

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        """Return LSP InitializeParams for the Solidity language server."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        return {  # type: ignore
            "locale": "en",
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
            "capabilities": {
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "didSave": True,
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {"snippetSupport": True},
                    },
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},  # type: ignore[arg-type]
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"],  # type: ignore[list-item]
                    },
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "initializationOptions": {},
        }

    def _get_wait_time_for_cross_file_referencing(self) -> float:
        # Small buffer for any post-indexing analysis the LSP performs after file-indexed events.
        return 3.0

    def _start_server(self) -> None:
        """Start the Solidity language server and wait for project indexing to finish."""

        def do_nothing(params: Any) -> None:
            return

        def register_capability_handler(params: Any) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        # Count .sol files in the project to know when indexing is complete.
        sol_files = glob.glob(os.path.join(self.repository_root_path, "**", "*.sol"), recursive=True)
        expected_count = len(sol_files)
        indexed_count = [0]
        all_indexed = threading.Event()

        def on_file_indexed(params: Any) -> None:
            indexed_count[0] += 1
            uri = (params or {}).get("uri", "")
            log.debug(f"Solidity LSP: file indexed ({indexed_count[0]}/{expected_count}): {uri}")
            if indexed_count[0] >= expected_count:
                all_indexed.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("custom/file-indexed", on_file_indexed)

        log.info("Starting Solidity language server process")
        self.server.start()

        initialize_params = self._get_initialize_params(self.repository_root_path)
        log.debug("Sending initialize request to Solidity language server")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Solidity server: {init_response}")

        if "documentSymbolProvider" in init_response.get("capabilities", {}):
            log.debug("Solidity server supports document symbols")
        else:
            log.warning("Solidity server does not report document symbol support")

        self.server.notify.initialized({})

        if expected_count > 0:
            log.info(f"Waiting for Solidity LSP to index {expected_count} .sol file(s)…")
            completed = all_indexed.wait(timeout=60)
            if completed:
                log.info(f"Solidity LSP indexing complete ({indexed_count[0]}/{expected_count} files indexed)")
            else:
                log.warning(
                    f"Solidity LSP indexing timed out ({indexed_count[0]}/{expected_count} files indexed). "
                    "Waiting additional 30s for slow environments (e.g., CI)."
                )
                sleep(30)
                log.info(f"Additional wait complete ({indexed_count[0]}/{expected_count} files indexed)")
        else:
            log.info("No .sol files found; skipping indexing wait")

        log.info("Solidity language server initialization complete")

    @override
    def request_text_document_diagnostics(
        self,
        relative_file_path: str,
        start_line: int = 0,
        end_line: int = -1,
        min_severity: int = 4,
    ) -> list[ls_types.Diagnostic]:
        self._validate_text_document_diagnostics_request(relative_file_path, start_line, end_line, min_severity)
        uri = self._get_validation_document_uri(relative_file_path)
        diagnostics_before_request = self._get_published_diagnostics_generation(uri)

        absolute_path = pathlib.Path(self.repository_root_path, relative_file_path)
        contents = absolute_path.read_text(encoding=self._encoding)
        lines = contents.split("\n")
        end_position = {
            "line": len(lines) - 1,
            "character": len(lines[-1]),
        }

        self.server.notify.did_open_text_document(
            {
                LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                    LSPConstants.URI: uri,
                    LSPConstants.LANGUAGE_ID: self.language_id,
                    LSPConstants.VERSION: 0,
                    LSPConstants.TEXT: contents,
                }
            }
        )
        try:
            self.server.notify.did_change_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                        LSPConstants.VERSION: 1,
                    },
                    LSPConstants.CONTENT_CHANGES: [  # type: ignore
                        {
                            LSPConstants.RANGE: {
                                "start": {"line": 0, "character": 0},
                                "end": end_position,
                            },
                            "text": contents,
                        }
                    ],
                }
            )
            diagnostics = self._wait_for_relevant_published_diagnostics(
                uri=uri,
                after_generation=diagnostics_before_request,
                timeout=self._get_published_diagnostics_wait_timeout(True),
                allow_cached=True,
            )
        finally:
            self.server.notify.did_close_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                    }
                }
            )

        if diagnostics is None:
            return []

        return self._filter_diagnostics(diagnostics, start_line, end_line, min_severity)

    def _get_validation_document_uri(self, relative_file_path: str) -> str:
        absolute_path = pathlib.Path(self.repository_root_path, relative_file_path)

        if os.name != "nt":
            return absolute_path.as_uri()

        path = absolute_path.as_posix()
        if len(path) >= 2 and path[1] == ":":
            path = f"{path[0].lower()}%3A{path[2:]}"

        return f"file:///{path.lstrip('/')}"
