"""
Language server implementation for tsgo — TypeScript 7's native Go-based compiler with built-in LSP.

tsgo (part of @typescript/native-preview) implements the Language Server Protocol natively,
without requiring Node.js or the traditional typescript-language-server wrapper.

Launch command: tsgo --lsp --stdio
"""

import logging
import os
import pathlib
import shutil
from typing import cast

from overrides import override
from sensai.util.logging import LogTime

from solidlsp.ls import LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection, build_npm_install_command
from .typescript_language_server import prefer_non_node_modules_definition

log = logging.getLogger(__name__)


class TsgoLanguageServer(SolidLanguageServer):
    """
    TypeScript support via tsgo — the native Go-based TypeScript 7 compiler with built-in LSP.

    tsgo is installed automatically via npm (``@typescript/native-preview``).
    It does not require the traditional typescript-language-server wrapper.

    You can pass the following entries in ls_specific_settings["typescript_tsgo"]:
        - tsgo_version: Version of @typescript/native-preview to install (default: "latest")
    """

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "node_modules",
            "dist",
            "build",
            "coverage",
            ".next",
            "out",
        ]

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """Install @typescript/native-preview via npm and return the path to the tsgo executable."""
            language_specific_config = self._custom_settings
            tsgo_version = language_specific_config.get("tsgo_version", "latest")
            npm_registry = language_specific_config.get("npm_registry")

            deps = RuntimeDependencyCollection(
                [
                    RuntimeDependency(
                        id="typescript-native-preview",
                        description="@typescript/native-preview (tsgo) package",
                        command=build_npm_install_command("@typescript/native-preview", tsgo_version, npm_registry),
                        platform_id="any",
                    ),
                ]
            )

            # Verify npm is installed
            is_npm_installed = shutil.which("npm") is not None
            assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

            tsgo_ls_dir = os.path.join(self._ls_resources_dir, "tsgo-lsp")
            tsgo_executable_path = os.path.join(tsgo_ls_dir, "node_modules", ".bin", "tsgo")

            # Check if installation is needed
            version_file = os.path.join(tsgo_ls_dir, ".installed_version")
            expected_version = tsgo_version

            needs_install = False
            if not os.path.exists(tsgo_executable_path):
                log.info(f"tsgo executable not found at {tsgo_executable_path}.")
                needs_install = True
            elif os.path.exists(version_file):
                with open(version_file) as f:
                    installed_version = f.read().strip()
                if installed_version != expected_version:
                    log.info(f"tsgo version mismatch: installed={installed_version}, expected={expected_version}. Reinstalling...")
                    needs_install = True
            else:
                log.info("tsgo version file not found. Reinstalling to ensure correct version...")
                needs_install = True

            if needs_install:
                log.info("Installing tsgo dependencies...")
                with LogTime("Installation of tsgo (typescript/native-preview)", logger=log):
                    deps.install(tsgo_ls_dir)
                with open(version_file, "w") as f:
                    f.write(expected_version)
                log.info("tsgo installed successfully")

            if not os.path.exists(tsgo_executable_path):
                raise FileNotFoundError(f"tsgo executable not found at {tsgo_executable_path}, something went wrong with the installation.")
            return tsgo_executable_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "--lsp", "--stdio"]

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "typescript",
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> "TsgoLanguageServer.DependencyProvider":
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params: dict = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "implementation": {"dynamicRegistration": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
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
        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting tsgo language server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request to tsgo LSP")
        init_response = self.server.send.initialize(initialize_params)

        assert "definitionProvider" in init_response.get("capabilities", {}), "tsgo did not report definitionProvider capability"

        self.server.notify.initialized({})

    @override
    def _get_preferred_definition(self, definitions: list) -> dict:
        return prefer_non_node_modules_definition(definitions)
