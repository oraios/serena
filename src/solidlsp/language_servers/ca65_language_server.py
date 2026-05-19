"""
CA65 language server integration for Serena.

Spawns the bundled `ca65-ls` (Python + pygls + tree-sitter-ca65) as a subprocess
over stdio. ca65-ls itself lives in a sibling package:
`github.com/JC-000/ca65-asm-serena-lsp` under `packages/ca65-ls/`.

Modeled on PyrightServer (also a Python-based, pip-installable LSP).
"""

import hashlib
import logging
import os
import pathlib
import sys
from collections.abc import Hashable
from pathlib import Path
from typing import cast

from overrides import override

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class Ca65LanguageServer(SolidLanguageServer):
    """
    CA65 (6502/65C02/65816 assembly) language server.

    ca65-ls runs as a Python module: `python -m ca65_ls.server --stdio`. Users
    install the `ca65-ls` package alongside Serena; pyproject.toml's optional
    extra `[ca65]` pulls it in.
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "ca65",
            solidlsp_settings,
        )

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            # Use the same interpreter Serena itself is running under. The user
            # must have installed ca65-ls into that environment (either via
            # Serena's `[ca65]` extra, or with `uv pip install ca65-ls`).
            return sys.executable

        def _create_launch_command(self, core_path: str) -> list[str]:
            return [core_path, "-m", "ca65_ls.server", "--stdio"]

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in (
            "build",
            "obj",
            ".ca65-ls",  # ca65-ls cache directory
        )

    @staticmethod
    def _get_initialize_params(repository_absolute_path: str) -> InitializeParams:
        initialize_params = {  # type: ignore
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": pathlib.Path(repository_absolute_path).as_uri(),
            "initializationOptions": {
                "projectRoot": repository_absolute_path,
                "buildDirs": ["build", "obj"],
                "cpu": "6502",
            },
            "capabilities": {
                "workspace": {
                    "workspaceEdit": {"documentChanges": True},
                    "symbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                },
                "textDocument": {
                    "synchronization": {"didSave": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                    "publishDiagnostics": {"relatedInformation": True},
                },
            },
            "workspaceFolders": [
                {
                    "uri": pathlib.Path(repository_absolute_path).as_uri(),
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return cast(InitializeParams, initialize_params)

    @override
    def _document_symbols_cache_fingerprint(self) -> Hashable | None:
        """Auto-invalidate Serena's on-disk document-symbol cache whenever the
        ca65-ls modules that shape its output change.

        Without this, Serena trusts its `.serena/cache/ca65/*.pkl` files across
        process restarts.  In development (with `--with-editable` installs)
        that means symbol output produced by an old ca65-ls keeps getting
        served even after a code update.  The fix is to include in the cache
        fingerprint:

          1. ca65-ls's installed package version (covers pinned releases), and
          2. a sha256 over the source files whose behavior directly affects
             document-symbol output (covers editable-install development).

        Any change to buffer/document.py, types.py, or server.py flips the
        hash, which flips this fingerprint, which causes Serena's cache to
        miss and rebuild from the live LSP.
        """
        try:
            import ca65_ls  # local import: avoid hard-failing if the user hasn't installed it yet
        except ImportError:
            return None

        version = getattr(ca65_ls, "__version__", "unknown")
        ca65_ls_root = Path(ca65_ls.__file__).parent
        source_files = [
            ca65_ls_root / "buffer" / "document.py",
            ca65_ls_root / "types.py",
            ca65_ls_root / "server.py",
        ]
        h = hashlib.sha256()
        for f in source_files:
            try:
                h.update(f.read_bytes())
            except OSError:
                # File missing (e.g. partial install); fold that into the hash
                # so the fingerprint still varies between "missing" and "present".
                h.update(b"<missing:" + str(f).encode() + b">")
        return (version, h.hexdigest()[:16])

    def _start_server(self) -> None:
        def do_nothing(_params: dict) -> None:
            return

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("window/logMessage", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting ca65-ls server process")
        self.server.start()

        params = self._get_initialize_params(self.repository_root_path)
        init_response = self.server.send.initialize(params)
        log.debug("ca65-ls initialize response: %s", init_response)

        assert "textDocumentSync" in init_response["capabilities"]
        assert "documentSymbolProvider" in init_response["capabilities"]
        assert "definitionProvider" in init_response["capabilities"]
        assert "referencesProvider" in init_response["capabilities"]
        assert "workspaceSymbolProvider" in init_response["capabilities"]
        assert "hoverProvider" in init_response["capabilities"]
        assert "renameProvider" in init_response["capabilities"]

        self.server.notify.initialized({})
