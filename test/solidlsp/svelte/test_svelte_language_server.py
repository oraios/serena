"""
Comprehensive test suite for Svelte language server integration.

Tests the dual language server architecture that provides full support for:
- Svelte components (.svelte files) via Svelte Language Server
- TypeScript/JavaScript files (.ts/.js files) via TypeScript Language Server
- Intelligent routing and symbol tree merging for mixed projects
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.svelte
class TestSvelteLanguageServer:
    """Test comprehensive Svelte/TypeScript language server integration."""

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_symbol_tree_discovery(self, language_server: SolidLanguageServer) -> None:
        """Test comprehensive symbol discovery across Svelte and TypeScript files."""
        symbols = language_server.request_full_symbol_tree()

        # Test Svelte component symbols
        assert SymbolUtils.symbol_tree_contains_name(symbols, "App"), "App component not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Button"), "Button component not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "handleClick"), "handleClick function not found in symbol tree"

        # Test TypeScript symbols from standalone .ts files
        assert SymbolUtils.symbol_tree_contains_name(symbols, "count"), "count store not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "User"), "User interface not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "formatName"), "formatName function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "ApiClient"), "ApiClient class not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_svelte_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test document symbol extraction from Svelte files."""
        file_path = "App.svelte"
        symbols, roots = language_server.request_document_symbols(file_path)

        # Should find various symbols in App.svelte
        symbol_names = [sym.get("name") for sym in symbols]
        assert "handleClick" in symbol_names, "Should find handleClick function"
        assert "handleIncrement" in symbol_names, "Should find handleIncrement function"
        assert "handleReset" in symbol_names, "Should find handleReset function"

        # Check that symbols have proper kinds
        handleClick_symbol = next((sym for sym in symbols if sym.get("name") == "handleClick"), None)
        assert handleClick_symbol is not None
        assert handleClick_symbol.get("kind") == 12, "handleClick should be a Function (kind 12)"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_typescript_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test document symbol extraction from TypeScript files."""
        file_path = "lib/utils.ts"
        symbols, roots = language_server.request_document_symbols(file_path)
        symbol_names = [sym.get("name") for sym in symbols]

        # Should find TypeScript symbols via dual language server architecture
        assert "formatName" in symbol_names, "Should find formatName function in utils.ts"
        assert "ApiClient" in symbol_names, "Should find ApiClient class in utils.ts"
        assert "validateEmail" in symbol_names, "Should find validateEmail function in utils.ts"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_button_component_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test symbol extraction from Svelte component files."""
        file_path = os.path.join("lib", "Button.svelte")
        symbols, roots = language_server.request_document_symbols(file_path)

        # Should find the handleClick function in Button.svelte
        symbol_names = [sym.get("name") for sym in symbols]
        assert "handleClick" in symbol_names, "Should find handleClick function in Button.svelte"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_dual_language_server_integration(self, language_server: SolidLanguageServer) -> None:
        """Test that both Svelte and TypeScript language servers work together."""
        # Test that we can analyze both file types in the same project

        # Svelte file analysis
        svelte_symbols, _ = language_server.request_document_symbols("App.svelte")
        svelte_names = [sym.get("name") for sym in svelte_symbols]
        assert "handleClick" in svelte_names, "Should analyze Svelte files"

        # TypeScript file analysis
        ts_symbols, _ = language_server.request_document_symbols("lib/store.ts")
        ts_names = [sym.get("name") for sym in ts_symbols]
        assert "User" in ts_names, "Should analyze TypeScript files"

        # Both should work without conflicts
        assert len(svelte_names) > 0 and len(ts_names) > 0, "Both language servers should be functional"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_mixed_project_symbol_coverage(self, language_server: SolidLanguageServer) -> None:
        """Test comprehensive symbol coverage in mixed Svelte/TypeScript projects."""
        symbols = language_server.request_full_symbol_tree()

        # Collect all symbols recursively to analyze coverage
        def collect_all_symbols(symbol_list):
            all_symbols = []
            for sym in symbol_list:
                all_symbols.append(sym)
                all_symbols.extend(collect_all_symbols(sym.get("children", [])))
            return all_symbols

        all_symbols = collect_all_symbols(symbols)

        # Categorize symbols by file type
        svelte_symbols = [s for s in all_symbols if s.get("location", {}).get("relativePath", "").endswith(".svelte")]
        ts_symbols = [s for s in all_symbols if s.get("location", {}).get("relativePath", "").endswith(".ts")]

        # Should have comprehensive coverage of both file types
        assert len(svelte_symbols) > 0, "Should have Svelte file symbols"
        assert len(ts_symbols) > 0, "Should have TypeScript file symbols"
        assert len(all_symbols) > 50, "Should have comprehensive symbol coverage"

        print(f"Symbol coverage: {len(svelte_symbols)} Svelte + {len(ts_symbols)} TypeScript = {len(all_symbols)} total")
