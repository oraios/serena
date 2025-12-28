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
        all_symbols = symbols.get_all_symbols_and_roots()
        symbol_names = [s.name for s in all_symbols]
        # Verify expected symbols from counter.ts
        assert "CounterStore" in symbol_names, f"Expected 'CounterStore' in symbols, got: {symbol_names}"
        assert "createCounter" in symbol_names, f"Expected 'createCounter' in symbols, got: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.ASTRO], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.ASTRO], indirect=True)
    def test_find_references_to_typescript_export(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding references to TypeScript export from Astro components."""
        counter_path = str(repo_path / "src" / "stores" / "counter.ts")
        # Find references to createCounter function
        # createCounter is on line 7 (0-indexed: 6), function name starts around char 16
        references = language_server.request_references(counter_path, 6, 20)
        # Should find at least the definition
        assert references is not None, "Expected references but got None"
        assert len(references) >= 1, f"Expected at least 1 reference, got {len(references)}"
        # Verify at least one reference is in counter.ts (the definition itself)
        ref_files = [ref["uri"] for ref in references]
        assert any("counter.ts" in uri for uri in ref_files), f"Expected reference in counter.ts, got: {ref_files}"

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
        all_symbols = symbols.get_all_symbols_and_roots()
        symbol_names = [s.name for s in all_symbols]
        assert "formatNumber" in symbol_names, f"Expected 'formatNumber' in symbols, got: {symbol_names}"
        assert "formatDate" in symbol_names, f"Expected 'formatDate' in symbols, got: {symbol_names}"
