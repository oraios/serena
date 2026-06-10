"""
Dexter language server support for Elixir.

Dexter (https://github.com/remoteoss/dexter) is a fast, full-featured Elixir
language server optimized for large codebases. Unlike Expert (the default
Elixir language server, see ``elixir_tools``), Dexter parses source files
directly as text and stores its index in SQLite, so it does not need to
compile the project before answering requests.

Installation
------------
The ``dexter`` binary must be installed manually and be available on PATH
(or configured via ``ls_specific_settings.elixir_dexter.ls_path``):

- Homebrew: ``brew install dexter-lsp``
- Mise: ``mise use -g aqua:remoteoss/dexter@latest``
- ASDF: ``asdf plugin add dexter https://github.com/remoteoss/dexter.git && asdf install dexter latest``

Official documentation: https://github.com/remoteoss/dexter
"""

import logging
import os
import pathlib
import shutil
import threading
from collections.abc import Hashable
from typing import Any, cast

from overrides import override

from solidlsp.ls import (
    LanguageServerDependencyProvider,
    LanguageServerDependencyProviderSinglePath,
    RawDocumentSymbol,
    SolidLanguageServer,
)
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class DexterLanguageServer(SolidLanguageServer):
    """
    Elixir language server implementation using Dexter (https://github.com/remoteoss/dexter),
    an alternative to Expert, which is the default for the language ``elixir``.

    You can pass the following entries in ``ls_specific_settings["elixir_dexter"]``:
        - ls_path: Path to the ``dexter`` executable, bypassing the PATH lookup.
        - initialization_options: Dict forwarded to Dexter via LSP ``initializationOptions``
          (e.g. ``followDelegates``, ``stdlibPath``, ``debug``; see the Dexter documentation).
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        """
        Creates a DexterLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        super().__init__(config, repository_root_path, None, "elixir", solidlsp_settings)
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Resolve the dexter executable from PATH or raise a helpful error if missing.
            Allows override via ls_specific_settings.elixir_dexter.ls_path.
            """
            dexter_path = shutil.which("dexter")
            if not dexter_path:
                raise FileNotFoundError(
                    "dexter is not installed or not found on PATH.\n"
                    "Please install Dexter, e.g.:\n"
                    "  Homebrew: brew install dexter-lsp\n"
                    "  Mise:     mise use -g aqua:remoteoss/dexter@latest\n"
                    "  ASDF:     asdf plugin add dexter https://github.com/remoteoss/dexter.git && asdf install dexter latest\n\n"
                    "Alternatively, set 'ls_path' in ls_specific_settings.elixir_dexter to the dexter executable.\n"
                    "For more details, see: https://github.com/remoteoss/dexter"
                )
            log.info(f"Using dexter at {dexter_path}")
            return dexter_path

        def _create_launch_command(self, core_path: str) -> list[str]:
            # Dexter speaks LSP over stdio via the "lsp" subcommand
            return [core_path, "lsp"]

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5.0  # give Dexter a moment to finish indexing before cross-file references are requested

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        # For Elixir projects, we should ignore:
        # - _build: compiled artifacts
        # - deps: dependencies
        # - node_modules: if the project has JavaScript components
        # - .elixir_ls / .expert: artifacts of other Elixir language servers
        # - .dexter: Dexter's SQLite index
        # - cover: coverage reports
        return super().is_ignored_dirname(dirname) or dirname in [
            "_build",
            "deps",
            "node_modules",
            ".elixir_ls",
            ".expert",
            ".dexter",
            "cover",
        ]

    @override
    def is_ignored_path(self, relative_path: str, ignore_unsupported_files: bool = True) -> bool:
        """Check if a path should be ignored for symbol indexing."""
        if relative_path.endswith("mix.exs"):
            # These are project configuration files, not source code with symbols to index
            return True

        return super().is_ignored_path(relative_path, ignore_unsupported_files)

    @override
    def _document_symbols_cache_fingerprint(self) -> Hashable:
        normalize_symbol_name_version = 1
        return normalize_symbol_name_version

    @override
    def _normalize_symbol_name(self, symbol: RawDocumentSymbol, relative_file_path: str) -> str:
        # Dexter reports function symbols with an arity suffix (e.g. "create_user/5"); strip it
        name = symbol["name"]
        base, sep, arity = name.rpartition("/")
        if sep and arity.isdigit():
            return base
        return name

    def _get_initialize_params(self) -> InitializeParams:
        """
        Returns the initialize params for the Dexter language server.
        """
        abs_path = os.path.abspath(self.repository_root_path)
        root_uri = pathlib.Path(abs_path).as_uri()
        initialization_options = self._custom_settings.get("initialization_options", {})
        initialize_params = {
            "processId": os.getpid(),
            "locale": "en",
            "rootPath": abs_path,
            "rootUri": root_uri,
            "initializationOptions": initialization_options,
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
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                },
                "window": {
                    "workDoneProgress": True,
                },
            },
            "workspaceFolders": [{"uri": root_uri, "name": os.path.basename(abs_path)}],
        }
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """Start the Dexter language server process and initialize the LSP connection."""

        def register_capability_handler(params: Any) -> None:
            log.debug(f"LSP: client/registerCapability: {params}")
            return

        def window_log_message(msg: Any) -> None:
            """Handle window/logMessage notifications from Dexter."""
            message_type = msg.get("type", 4)  # 1=Error, 2=Warning, 3=Info, 4=Log
            message_text = msg.get("message", "")
            if message_type == 1:
                log.error(f"Dexter: {message_text}")
            elif message_type == 2:
                log.warning(f"Dexter: {message_text}")
            else:
                log.debug(f"Dexter: {message_text}")

        def do_nothing(params: Any) -> None:
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("window/workDoneProgress/create", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.debug("Starting Dexter server process")
        self.server.start()
        initialize_params = self._get_initialize_params()

        log.debug("Sending initialize request to Dexter")
        init_response = self.server.send.initialize(initialize_params)
        assert "capabilities" in init_response, f"Missing capabilities in initialize response: {init_response}"

        self.server.notify.initialized({})

        # Dexter builds its index in the background after initialization; indexing is fast
        # (seconds even on large codebases), so no explicit readiness signal needs to be awaited.
        self.server_ready.set()
