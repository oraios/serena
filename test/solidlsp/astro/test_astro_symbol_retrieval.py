"""
Symbol retrieval tests for Astro language server.

Tests cover:
- Containing symbol requests
- Referencing symbol requests
- Cross-file type resolution
- Import resolution

Template: test_vue_symbol_retrieval.py
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.astro
class TestAstroSymbolRetrieval:
    """Symbol retrieval functionality tests."""

    @pytest.mark.parametrize("language_server", [Language.ASTRO], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ASTRO], indirect=True)
    def test_get_containing_symbol_in_typescript(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding containing symbol in .ts file within Astro project."""
        counter_path = str(repo_path / "src" / "stores" / "counter.ts")
        # Request document symbols to verify we can get symbols from TS files
        symbols = language_server.request_document_symbols(counter_path)
        assert symbols is not None, "Expected document symbols but got None"
        all_symbols, _roots = symbols.get_all_symbols_and_roots()
        symbol_names = [s["name"] for s in all_symbols]
        # Verify expected symbols from counter.ts
        assert "CounterStore" in symbol_names, f"Expected 'CounterStore' in symbols, got: {symbol_names}"
        assert "createCounter" in symbol_names, f"Expected 'createCounter' in symbols, got: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.ASTRO], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ASTRO], indirect=True)
    def test_find_references_to_typescript_export(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding references to a TypeScript export from an .astro component.

        createCounter is defined in counter.ts and imported + called in
        src/pages/index.astro. This exercises the dual-server cross-file path: the
        companion tsserver (with @astrojs/ts-plugin) must resolve the .astro usage.
        """
        counter_path = str(repo_path / "src" / "stores" / "counter.ts")
        # createCounter is on line 7 (0-indexed: 6), function name starts around char 16
        references = language_server.request_references(counter_path, 6, 20)
        assert references is not None, "Expected references but got None"
        # (file basename, 0-indexed start line) for every reference found
        locations = {(ref["uri"].rsplit("/", 1)[-1], ref["range"]["start"]["line"]) for ref in references}
        # Definition in counter.ts (line 6) plus the import (line 4) and the call (line 7) in index.astro.
        # The index.astro hits require the companion tsserver's @astrojs/ts-plugin awareness to resolve.
        assert ("counter.ts", 6) in locations, f"Expected the definition at counter.ts:6, got: {sorted(locations)}"
        assert ("index.astro", 4) in locations, f"Expected the import at index.astro:4, got: {sorted(locations)}"
        assert ("index.astro", 7) in locations, f"Expected the call at index.astro:7, got: {sorted(locations)}"

    @pytest.mark.parametrize("language_server", [Language.ASTRO], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ASTRO], indirect=True)
    def test_go_to_definition_from_typescript(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test go-to-definition within TypeScript source."""
        counter_path = str(repo_path / "src" / "stores" / "counter.ts")
        # In createCounter function, CounterStore return type is on line 7 (0-indexed: 6)
        definition_list = language_server.request_definition(counter_path, 6, 35)
        assert definition_list, "Expected at least one definition"
        # Should point to CounterStore interface definition
        definition = definition_list[0]
        assert definition["uri"].endswith("counter.ts"), f"Expected counter.ts, got: {definition['uri']}"
        # CounterStore is defined at line 0
        assert definition["range"]["start"]["line"] == 0, f"Expected line 0, got: {definition['range']['start']['line']}"

    @pytest.mark.parametrize("language_server", [Language.ASTRO], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ASTRO], indirect=True)
    def test_format_utils_symbols(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that format.ts utility file symbols are accessible."""
        format_path = str(repo_path / "src" / "utils" / "format.ts")
        symbols = language_server.request_document_symbols(format_path)
        assert symbols is not None, "Expected document symbols but got None"
        all_symbols, _roots = symbols.get_all_symbols_and_roots()
        symbol_names = [s["name"] for s in all_symbols]
        assert "formatNumber" in symbol_names, f"Expected 'formatNumber' in symbols, got: {symbol_names}"
        assert "formatDate" in symbol_names, f"Expected 'formatDate' in symbols, got: {symbol_names}"
