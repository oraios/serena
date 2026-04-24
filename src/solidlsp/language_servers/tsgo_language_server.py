"""
Language server implementation for tsgo — TypeScript 7's native Go-based compiler with built-in LSP.

tsgo (part of @typescript/native-preview) implements the Language Server Protocol natively,
without requiring Node.js or the traditional typescript-language-server wrapper.

Launch command: tsgo --lsp --stdio
"""

import logging
import os
import pathlib
import subprocess
from typing import cast

from overrides import override

from solidlsp.ls import LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .typescript_language_server import prefer_non_node_modules_definition

log = logging.getLogger(__name__)


class TsgoLanguageServer(SolidLanguageServer):
    """
    TypeScript support via tsgo — the native Go-based TypeScript 7 compiler with built-in LSP.

    tsgo does not require Node.js. It must be installed separately
    (e.g. via ``npm install -g @typescript/native-preview``).

    You can pass the following entries in ls_specific_settings["typescript_tsgo"]:
        - ls_path: Path to the tsgo binary (default: discovered from PATH)
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
            """Locate the tsgo binary on the system. tsgo must be pre-installed by the user."""
            import shutil

            tsgo_path = shutil.which("tsgo")
            if tsgo_path is None:
                raise RuntimeError(
                    "tsgo is not installed or not found in PATH.\n"
                    "Install it via: npm install -g @typescript/native-preview\n"
                    "Or set the 'ls_path' option in ls_specific_settings['typescript_tsgo'] "
                    "to point to your tsgo binary."
                )

            # Verify it works
            try:
                result = subprocess.run([tsgo_path, "--version"], capture_output=True, text=True, check=False, timeout=10)
                if result.returncode == 0:
                    log.info(f"Found tsgo: {result.stdout.strip()}")
                else:
                    log.warning(f"tsgo --version returned non-zero exit code: {result.returncode}")
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                raise RuntimeError(f"Failed to verify tsgo binary at {tsgo_path}: {e}") from e

            return tsgo_path

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

        assert "definitionProvider" in init_response.get("capabilities", {}), (
            "tsgo did not report definitionProvider capability"
        )

        self.server.notify.initialized({})

    @override
    def _get_preferred_definition(self, definitions: list) -> dict:
        return prefer_non_node_modules_definition(definitions)
