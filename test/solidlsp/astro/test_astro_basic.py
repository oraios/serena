"""
Basic integration and symbol retrieval tests for the Astro language server.
"""

import os
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.conftest import document_symbol_names, request_all_symbols

pytestmark = pytest.mark.astro


class TestAstroLanguageServerBasics:
    """Smoke, symbol retrieval, and dual-server coordination tests for Astro."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.ASTRO], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_card_document_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "components", "Card.astro")
        names = document_symbol_names(language_server, file_path)

        # Frontmatter symbols
        assert "Props" in names
        assert "formatTitle" in names

        # Template elements
        assert any(n in names for n in ("li", "a", "h2", "p"))

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_layout_document_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "layouts", "Layout.astro")
        names = document_symbol_names(language_server, file_path)

        assert "Props" in names
        assert "title" in names

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_index_document_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "pages", "index.astro")
        names = document_symbol_names(language_server, file_path)

        assert "pageTitle" in names
        assert any(n in names for n in ("main", "h1", "Card", "Layout"))

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_typescript_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Verify TypeScript files in Astro project have document symbols routed to companion TS server."""
        file_path = os.path.join("src", "stores", "counter.ts")
        symbols = language_server.request_document_symbols(file_path)
        assert symbols is not None, "Expected document symbols from companion TypeScript server"
        all_symbols, _roots = symbols.get_all_symbols_and_roots()
        symbol_names = [s["name"] for s in all_symbols]
        assert "CounterStore" in symbol_names
        assert "createCounter" in symbol_names

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_format_utils_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "utils", "format.ts")
        symbols = language_server.request_document_symbols(file_path)
        assert symbols is not None
        all_symbols, _roots = symbols.get_all_symbols_and_roots()
        symbol_names = [s["name"] for s in all_symbols]
        assert "formatNumber" in symbol_names
        assert "formatDate" in symbol_names

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_typescript_companion_server_starts(self, language_server: SolidLanguageServer) -> None:
        """Verify companion TypeScript server starts and attaches to AstroLanguageServer."""
        from solidlsp.language_servers.astro_language_server import AstroLanguageServer

        astro_ls = language_server.language_server
        assert isinstance(astro_ls, AstroLanguageServer), "Expected AstroLanguageServer instance"
        assert astro_ls._ts_server is not None, "Expected companion TypeScript server to be initialized"
        assert astro_ls._ts_server_started, "Expected companion TypeScript server to be started"

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_find_definition_within_typescript(self, language_server: SolidLanguageServer) -> None:
        """Verify go-to-definition within TypeScript files in Astro project."""
        file_path = os.path.join("src", "stores", "counter.ts")
        # Line 7 (0-indexed line 6), char 35: CounterStore return type annotation
        definitions = language_server.request_definition(file_path, 6, 35)
        assert definitions, "Expected at least one definition location"
        def_loc = definitions[0]
        assert def_loc["uri"].endswith("counter.ts")
        assert def_loc["range"]["start"]["line"] == 0

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_find_references_within_typescript(self, language_server: SolidLanguageServer) -> None:
        """Verify reference finding within TypeScript file."""
        file_path = os.path.join("src", "stores", "counter.ts")
        # CounterStore interface on line 0, char 20
        references = language_server.request_references(file_path, 0, 20)
        assert references, "Expected at least one reference location"
        locations = {(ref["uri"].rsplit("/", 1)[-1], ref["range"]["start"]["line"]) for ref in references}
        assert ("counter.ts", 0) in locations
        assert ("counter.ts", 6) in locations

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_full_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        relative_paths: set[str] = set()
        for s in all_symbols:
            loc = s.get("location")
            if isinstance(loc, dict):
                rel = loc.get("relativePath")
                if isinstance(rel, str):
                    relative_paths.add(rel.replace("\\", "/"))
        assert any("Card.astro" in p for p in relative_paths)
        assert any("index.astro" in p for p in relative_paths)
