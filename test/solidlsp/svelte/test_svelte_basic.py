import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.svelte
class TestSvelteLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "App"), "App component not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Button"), "Button component not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "handleClick"), "handleClick function not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols work for Svelte files"""
        file_path = os.path.join("App.svelte")
        symbols, roots = language_server.request_document_symbols(file_path)

        # Should find various symbols in App.svelte
        symbol_names = [sym.get("name") for sym in symbols]
        assert "handleClick" in symbol_names, "Should find handleClick function"
        assert "incrementCount" in symbol_names, "Should find incrementCount function"

        # Check that symbols have proper kinds
        handleClick_symbol = next((sym for sym in symbols if sym.get("name") == "handleClick"), None)
        assert handleClick_symbol is not None
        assert handleClick_symbol.get("kind") == 12, "handleClick should be a Function (kind 12)"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_button_component_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test that Button component symbols are properly detected"""
        file_path = os.path.join("lib", "Button.svelte")
        symbols, roots = language_server.request_document_symbols(file_path)

        # Should find the handleClick function in Button.svelte
        symbol_names = [sym.get("name") for sym in symbols]
        assert "handleClick" in symbol_names, "Should find handleClick function in Button.svelte"
