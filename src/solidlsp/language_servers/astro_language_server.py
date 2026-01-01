"""
Astro Language Server implementation using @astrojs/language-server with companion TypeScript LS.
Operates in hybrid mode: Astro LS handles .astro files, TypeScript LS handles .ts/.js files.
"""

import logging
import os
import pathlib
import shutil
import threading
from typing import Any

from overrides import override

from solidlsp import ls_types
from solidlsp.companion_ls import CompanionLanguageServer
from solidlsp.embedded_language_config import EmbeddedLanguageConfig
from solidlsp.language_servers.common import RuntimeDependency, RuntimeDependencyCollection
from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.settings import SolidLSPSettings
from solidlsp.typescript_companion import (
    create_typescript_companion_config,
    prefer_non_node_modules_definition,
)

log = logging.getLogger(__name__)


class AstroTypeScriptServer(TypeScriptLanguageServer):
    """TypeScript LS configured with @astrojs/ts-plugin for Astro file support."""

    @classmethod
    @override
    def get_language_enum_instance(cls) -> Language:
        return Language.TYPESCRIPT

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """Return the correct language ID for files.

        Astro files must be opened with language ID "astro" for the @astrojs/ts-plugin
        to process them correctly.
        """
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".astro":
            return "astro"
        elif ext in (".ts", ".tsx", ".mts", ".cts"):
            return "typescript"
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        else:
            return "typescript"

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        solidlsp_settings: SolidLSPSettings,
        astro_plugin_path: str,
        tsdk_path: str,
        ts_ls_executable_path: list[str],
    ):
        """Initialize the AstroTypeScriptServer with Astro plugin configuration.

        :param config: Language server configuration
        :param repository_root_path: Root path of the repository
        :param solidlsp_settings: SolidLSP settings
        :param astro_plugin_path: Path to the @astrojs/ts-plugin
        :param tsdk_path: Path to the TypeScript SDK
        :param ts_ls_executable_path: Path to the TypeScript language server executable
        """
        self._astro_plugin_path = astro_plugin_path
        self._custom_tsdk_path = tsdk_path
        super().__init__(config, repository_root_path, solidlsp_settings, executable_path=ts_ls_executable_path)

    @override
    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        params = super()._get_initialize_params(repository_absolute_path)

        params["initializationOptions"] = {
            "plugins": [
                {
                    "name": "@astrojs/ts-plugin",
                    "location": self._astro_plugin_path,
                    "languages": ["astro"],
                }
            ],
            "tsserver": {
                "path": self._custom_tsdk_path,
            },
        }

        if "workspace" in params["capabilities"]:
            params["capabilities"]["workspace"]["executeCommand"] = {"dynamicRegistration": True}

        return params

    @override
    def _start_server(self) -> None:
        def workspace_configuration_handler(params: dict[str, Any]) -> list[dict[str, Any]]:
            items = params.get("items", [])
            return [{} for _ in items]

        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        super()._start_server()


class AstroLanguageServer(CompanionLanguageServer):
    """
    Language server for Astro components using @astrojs/language-server with companion TypeScript LS.

    You can pass the following entries in ls_specific_settings["astro"]:
        - astro_language_server_version: Version of @astrojs/language-server to install (default: "2.16.2")

    Note: TypeScript versions are configured via ls_specific_settings["typescript"]:
        - typescript_version: Version of TypeScript to install (default: "5.9.3")
        - typescript_language_server_version: Version of typescript-language-server to install (default: "5.1.3")
    """

    TS_SERVER_READY_TIMEOUT = 5.0
    ASTRO_SERVER_READY_TIMEOUT = 3.0
    # Windows requires more time due to slower I/O and process operations.
    ASTRO_INDEXING_WAIT_TIME = 4.0 if os.name == "nt" else 2.0

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        astro_lsp_executable_path, self.tsdk_path, self._ts_ls_cmd = self._setup_runtime_dependencies(config, solidlsp_settings)
        self._astro_ls_dir = os.path.join(self.ls_resources_dir(solidlsp_settings), "astro-lsp")
        self.server_ready = threading.Event()
        super().__init__(
            config,
            repository_root_path,
            ProcessLaunchInfo(cmd=astro_lsp_executable_path, cwd=repository_root_path),
            "astro",
            solidlsp_settings,
        )

    @override
    def _get_domain_file_extension(self) -> str:
        """Return the primary file extension for Astro files."""
        return ".astro"

    @override
    def _get_embedded_language_configs(self) -> list[EmbeddedLanguageConfig]:
        """Define TypeScript as the embedded language for Astro files."""
        return [
            create_typescript_companion_config(
                file_patterns=["*.astro"],
                handles_definitions=True,
                handles_references=True,
                handles_rename=True,
            )
        ]

    @override
    def _create_companion_server(self, config: EmbeddedLanguageConfig) -> SolidLanguageServer:
        """Create the companion TypeScript server for Astro files."""
        if config.language_id != "typescript":
            raise ValueError(f"AstroLanguageServer only supports TypeScript companion, got: {config.language_id}")

        astro_ts_plugin_path = os.path.join(self._astro_ls_dir, "node_modules", "@astrojs", "ts-plugin")

        ts_config = LanguageServerConfig(
            code_language=Language.TYPESCRIPT,
            trace_lsp_communication=False,
        )

        log.info("Creating companion AstroTypeScriptServer")
        return AstroTypeScriptServer(
            config=ts_config,
            repository_root_path=self.repository_root_path,
            solidlsp_settings=self._solidlsp_settings,
            astro_plugin_path=astro_ts_plugin_path,
            tsdk_path=self.tsdk_path,
            ts_ls_executable_path=self._ts_ls_cmd,
        )

    @override
    def _ensure_domain_files_indexed(self) -> None:
        """Index Astro files on companion servers with additional wait time for TS server processing."""
        from time import sleep

        if self._domain_files_indexed:
            return

        # Call base implementation to do the actual indexing
        super()._ensure_domain_files_indexed()

        # Additional wait time for TypeScript server to process indexed Astro files
        sleep(self.ASTRO_INDEXING_WAIT_TIME)
        log.debug("Wait period after Astro file indexing complete")

    @override
    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        """Prefer non-node_modules definitions when multiple are found."""
        return prefer_non_node_modules_definition(definitions)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        """Include Astro-specific directories to ignore."""
        return super().is_ignored_dirname(dirname) or dirname in [".astro", "dist"]

    @override
    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        """Return correct language ID for files."""
        ext = os.path.splitext(relative_file_path)[1].lower()
        if ext == ".astro":
            return "astro"
        elif ext in (".ts", ".tsx", ".mts", ".cts"):
            return "typescript"
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        else:
            return "typescript"

    @classmethod
    def _setup_runtime_dependencies(
        cls, config: LanguageServerConfig, solidlsp_settings: SolidLSPSettings
    ) -> tuple[list[str], str, list[str]]:
        if shutil.which("node") is None:
            raise RuntimeError("node is not installed or isn't in PATH. Please install NodeJS and try again.")
        if shutil.which("npm") is None:
            raise RuntimeError("npm is not installed or isn't in PATH. Please install npm and try again.")

        # Get TypeScript version settings from TypeScript language server settings
        typescript_config = solidlsp_settings.get_ls_specific_settings(Language.TYPESCRIPT)
        typescript_version = typescript_config.get("typescript_version", "5.9.3")
        typescript_language_server_version = typescript_config.get("typescript_language_server_version", "5.1.3")
        astro_config = solidlsp_settings.get_ls_specific_settings(Language.ASTRO)
        astro_language_server_version = astro_config.get("astro_language_server_version", "2.16.2")

        deps = RuntimeDependencyCollection(
            [
                RuntimeDependency(
                    id="astro-language-server",
                    description="Astro language server package",
                    command=["npm", "install", "--prefix", "./", f"@astrojs/language-server@{astro_language_server_version}"],
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript",
                    description="TypeScript (required for tsdk)",
                    command=["npm", "install", "--prefix", "./", f"typescript@{typescript_version}"],
                    platform_id="any",
                ),
                RuntimeDependency(
                    id="typescript-language-server",
                    description="TypeScript language server (for Astro LS tsserver forwarding)",
                    command=[
                        "npm",
                        "install",
                        "--prefix",
                        "./",
                        f"typescript-language-server@{typescript_language_server_version}",
                    ],
                    platform_id="any",
                ),
            ]
        )

        astro_ls_dir = os.path.join(cls.ls_resources_dir(solidlsp_settings), "astro-lsp")
        astro_executable_path = os.path.join(astro_ls_dir, "node_modules", ".bin", "astro-ls")
        ts_ls_executable_path = os.path.join(astro_ls_dir, "node_modules", ".bin", "typescript-language-server")

        if os.name == "nt":
            astro_executable_path += ".cmd"
            ts_ls_executable_path += ".cmd"

        tsdk_path = os.path.join(astro_ls_dir, "node_modules", "typescript", "lib")

        # Check if installation is needed based on executables AND version
        version_file = os.path.join(astro_ls_dir, ".installed_version")
        expected_version = f"{astro_language_server_version}_{typescript_version}_{typescript_language_server_version}"

        needs_install = False
        if not os.path.exists(astro_executable_path) or not os.path.exists(ts_ls_executable_path):
            log.info("Astro/TypeScript Language Server executables not found.")
            needs_install = True
        elif os.path.exists(version_file):
            with open(version_file, encoding="utf-8") as f:
                installed_version = f.read().strip()
            if installed_version != expected_version:
                log.info(
                    f"Astro Language Server version mismatch: installed={installed_version}, expected={expected_version}. Reinstalling..."
                )
                needs_install = True
        else:
            # No version file exists, install to ensure correct version
            log.info("Astro Language Server version file not found, installing...")
            needs_install = True

        if needs_install:
            log.info("Installing Astro/TypeScript Language Server dependencies...")
            deps.install(astro_ls_dir)
            # Write version marker file
            with open(version_file, "w", encoding="utf-8") as f:
                f.write(expected_version)
            log.info("Astro language server dependencies installed successfully")

        if not os.path.exists(astro_executable_path):
            raise FileNotFoundError(
                f"astro-ls executable not found at {astro_executable_path}, something went wrong with the installation."
            )

        if not os.path.exists(ts_ls_executable_path):
            raise FileNotFoundError(
                f"typescript-language-server executable not found at {ts_ls_executable_path}, something went wrong with the installation."
            )

        return [astro_executable_path, "--stdio"], tsdk_path, [ts_ls_executable_path, "--stdio"]

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """Return Astro-specific initialization parameters."""
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True, "linkSupport": True},
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
            "initializationOptions": {
                "typescript": {
                    "tsdk": self.tsdk_path,
                },
            },
        }
        return initialize_params  # type: ignore

    @override
    def _start_server(self) -> None:
        """Start the Astro language server with custom handlers."""
        # Start companion servers (TypeScript) first
        self._start_companions()

        # Set up Astro-specific request handlers
        def register_capability_handler(params: dict[str, Any]) -> None:
            if "registrations" not in params:
                log.warning("client/registerCapability received params without 'registrations'")
                return
            return

        def configuration_handler(params: dict[str, Any]) -> list[dict[str, Any]]:
            items = params.get("items", [])
            return [{} for _ in items]

        def do_nothing(_params: dict[str, Any]) -> None:
            return

        def window_log_message(msg: dict[str, Any]) -> None:
            log.info(f"LSP: window/logMessage: {msg}")
            message_text = msg.get("message", "")
            if "initialized" in message_text.lower() or "ready" in message_text.lower():
                log.info("Astro language server ready signal detected")
                self.server_ready.set()
                self.completions_available.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Astro server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Astro server: {init_response}")

        assert init_response["capabilities"]["textDocumentSync"] in [1, 2]

        self.server.notify.initialized({})

        log.info("Waiting for Astro language server to be ready...")
        if not self.server_ready.wait(timeout=self.ASTRO_SERVER_READY_TIMEOUT):
            log.info("Timeout waiting for Astro server ready signal, proceeding anyway")
            self.server_ready.set()
            self.completions_available.set()
        else:
            log.info("Astro server initialization complete")

    def _find_tsconfig_for_file(self, relative_file_path: str) -> str | None:
        """Find the nearest tsconfig.json for a file."""
        file_path = pathlib.Path(self.repository_root_path) / relative_file_path
        for parent in file_path.parents:
            tsconfig = parent / "tsconfig.json"
            if tsconfig.exists():
                return str(tsconfig)
            if parent == pathlib.Path(self.repository_root_path):
                break
        return None

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """Return wait time for cross-file reference operations."""
        return self.ASTRO_INDEXING_WAIT_TIME

    @override
    def stop(self, shutdown_timeout: float = 2.0) -> None:
        """Stop the Astro language server and companions."""
        self.server_ready.clear()
        super().stop(shutdown_timeout)
