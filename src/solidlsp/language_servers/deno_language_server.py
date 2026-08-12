"""
Provides Deno-specific instantiation of the LanguageServer class, using the
language server built into the Deno CLI (``deno lsp``).
"""

import logging
import shutil

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class DenoLanguageServer(SolidLanguageServer):
    """
    Deno instantiation of the LanguageServer class, backed by ``deno lsp``.

    Serves TypeScript/JavaScript in Deno projects. Unlike the plain
    typescript-language-server, ``deno lsp`` understands Deno-specific module
    resolution (``npm:`` / ``jsr:`` / ``https:`` imports) and the ``Deno.*``
    global namespace.

    This server overlaps the TypeScript server on file extensions and is therefore
    marked experimental: it is not auto-detected and must be selected explicitly via
    ``languages: [deno]`` in ``project.yml``.
    """

    @classmethod
    def supports_implementation_request(cls) -> bool:
        return True

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "typescript",
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # node_modules appears in Deno projects using npm compatibility; vendor/ holds
        # vendored remote dependencies. Neither should be indexed as project sources.
        return super().is_ignored_dirname(dirname) or dirname in ["node_modules", "vendor", "dist", "build"]

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """Return the path to the ``deno`` executable (the language server ships with it)."""
            deno_path = shutil.which("deno")
            if deno_path is None:
                raise FileNotFoundError(
                    "The 'deno' executable was not found on PATH. Install Deno "
                    "(https://docs.deno.com/runtime/getting_started/installation/) — it bundles "
                    "the language server used here — and ensure 'deno' is on your PATH."
                )
            return deno_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "lsp"]

    def _get_language_id_for_file(self, relative_file_path: str) -> str:
        # deno lsp relies on the correct languageId; .tsx/.jsx in particular must not
        # be sent as plain "typescript" or symbol ranges get truncated at JSX expressions.
        if relative_file_path.endswith(".tsx"):
            return "typescriptreact"
        if relative_file_path.endswith(".jsx"):
            return "javascriptreact"
        if relative_file_path.endswith((".js", ".mjs", ".cjs")):
            return "javascript"
        return "typescript"

    def _create_base_initialize_params(self) -> dict:
        return {
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
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "configuration": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            # deno lsp reads its settings from initializationOptions; enabling the server
            # and the linter mirrors the defaults of the official VS Code Deno extension.
            "initializationOptions": {
                "enable": True,
                "lint": True,
                "unstable": False,
            },
        }

    def _start_server(self) -> None:
        """Start the ``deno lsp`` process and drive the LSP initialize handshake."""

        def register_capability_handler(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info(f"LSP: window/logMessage: {msg}")

        def do_nothing(params: dict) -> None:
            return

        def configuration_handler(params: dict) -> list:
            # deno lsp requests workspace/configuration during startup; return an empty
            # settings object per requested item so it proceeds with its defaults.
            return [{} for _ in params.get("items", [])]

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", configuration_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        # Deno-specific notifications emitted after config discovery; no action needed.
        self.server.on_notification("deno/didRefreshDenoConfigurationTree", do_nothing)
        self.server.on_notification("deno/didChangeDenoConfiguration", do_nothing)

        log.info("Starting deno lsp server process")
        self.server.start()
        initialize_params = self._create_initialize_params()

        log.info("Sending initialize request from LSP client to deno lsp and awaiting response")
        init_response = self.server.send.initialize(initialize_params)

        assert "textDocumentSync" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
