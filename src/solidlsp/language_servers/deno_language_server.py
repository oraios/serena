"""
Provides Deno specific instantiation of the LanguageServer class using the built-in `deno lsp`.
Contains various configurations and settings specific to Deno.
"""

import logging
import os
import pathlib
import platform
import shutil
import threading

from overrides import override
from sensai.util.logging import LogTime

from solidlsp import ls_types
from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection
from .typescript_language_server import prefer_non_node_modules_definition

log = logging.getLogger(__name__)


class DenoLanguageServer(SolidLanguageServer):
    """
    Provides Deno specific instantiation of the LanguageServer class using the built-in `deno lsp`.

    If Deno is not found on the system PATH, it will be automatically installed via the official npm package.

    This language server must be explicitly configured in .serena/project.yml
    (it is not auto-detected to avoid conflicts with the TypeScript language server).
    Do not configure both TYPESCRIPT and DENO for the same project.

    You can pass the following entries in ls_specific_settings["deno"]:
        - ls_path: Path to the Deno executable (default: auto-detected from PATH, falls back to npm install)
        - deno_version: Pin a specific Deno version for npm install (default: latest)
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "typescript",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

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

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """Find or install the Deno executable.

            First checks if Deno is available on PATH. If not, falls back to
            installing via npm (using the official 'deno' npm package).
            """
            deno_path = shutil.which("deno")
            if deno_path is not None:
                return deno_path

            # Fall back to npm-based installation
            is_node_installed = shutil.which("node") is not None
            is_npm_installed = shutil.which("npm") is not None
            assert is_node_installed and is_npm_installed, (
                "Deno is not installed and Node.js/npm are not available for auto-install. "
                "Please install Deno (https://deno.com) or Node.js and try again."
            )

            deno_version = self._custom_settings.get("deno_version")
            install_spec = f"deno@{deno_version}" if deno_version else "deno"
            deps = RuntimeDependencyCollection([
                RuntimeDependency(
                    id="deno",
                    description="Deno runtime (official npm distribution)",
                    command=["npm", "install", "--prefix", "./", install_spec],
                    platform_id="any",
                ),
            ])

            deno_ls_dir = os.path.join(self._ls_resources_dir, "deno-lsp")
            binary_name = "deno.exe" if platform.system() == "Windows" else "deno"
            deno_executable = os.path.join(deno_ls_dir, "node_modules", "deno", binary_name)

            # Check if installation is needed
            version_file = os.path.join(deno_ls_dir, ".installed_version")
            expected_version = deno_version or "latest"

            needs_install = False
            if not os.path.exists(deno_executable):
                log.info(f"Deno executable not found at {deno_executable}.")
                needs_install = True
            elif deno_version and os.path.exists(version_file):
                with open(version_file) as f:
                    installed_version = f.read().strip()
                if installed_version != expected_version:
                    log.info(f"Deno version mismatch: installed={installed_version}, expected={expected_version}. Reinstalling...")
                    needs_install = True

            if needs_install:
                log.info("Installing Deno via npm...")
                with LogTime("Installation of Deno runtime", logger=log):
                    deps.install(deno_ls_dir)
                with open(version_file, "w") as f:
                    f.write(expected_version)
                log.info("Deno installed successfully via npm")

            if not os.path.exists(deno_executable):
                raise FileNotFoundError(f"Deno executable not found at {deno_executable}, something went wrong with the installation.")
            return deno_executable

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "lsp"]

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True},
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "rename": {"prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "configuration": True,
                },
            },
            "initializationOptions": {
                "enable": True,
            },
            "workspaceFolders": [{
                "uri": root_uri,
                "name": os.path.basename(repository_absolute_path),
            }],
        }
        return initialize_params  # type: ignore

    def _start_server(self) -> None:
        """Starts the Deno Language Server, waits for the server to be ready."""

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            return

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def workspace_configuration_handler(params: dict) -> list:  # type: ignore[type-arg]
            """Handle workspace/configuration requests from Deno LSP."""
            result: list[dict | None] = []
            for item in params.get("items", []):
                if item.get("section") == "deno":
                    result.append({ "enable": True })
                elif item.get("section") in ("typescript", "javascript"):
                    result.append({
                        "preferences": {
                            "importModuleSpecifierPreference": "relative",
                        },
                    })
                else:
                    result.append(None)
            return result

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)

        log.info("Starting Deno server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to Deno LSP server and awaiting response")
        init_response = self.server.send.initialize(initialize_params)
        log.debug(f"Received initialize response from Deno server: {init_response}")

        assert "capabilities" in init_response
        assert "textDocumentSync" in init_response["capabilities"]
        assert "completionProvider" in init_response["capabilities"]

        self.server.notify.initialized({})

        # Deno LSP is typically ready quickly after initialized notification
        log.info("Deno server initialization complete")
        self.server_ready.set()

    @override
    def _get_preferred_definition(self, definitions: list[ls_types.Location]) -> ls_types.Location:
        return prefer_non_node_modules_definition(definitions)
