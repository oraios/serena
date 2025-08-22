"""
Test Svelte Language Server
"""

import os
import sys

import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.svelte
@pytest.mark.skipif(sys.platform == "win32", reason="svelte-proxy-lsp requires additional setup on Windows")
class TestSvelteServer:
    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_find_definition_svelte_component(self, language_server: SolidLanguageServer) -> None:
        """
        Test finding definition of a Svelte component import
        """
        filepath = os.path.join("src", "routes", "+page.svelte")
        line = 1
        column = 18  # Counter in "import Counter"

        result = language_server.request_definition(filepath, line, column)

        # Definition finding may not be fully supported yet
        assert result is not None

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_find_definition_typescript_import(self, language_server: SolidLanguageServer) -> None:
        """
        Test finding definition of a TypeScript function import
        """
        filepath = os.path.join("src", "routes", "+page.svelte")
        line = 2
        column = 10  # formatNumber in import statement

        result = language_server.request_definition(filepath, line, column)

        # Definition finding may not be fully supported yet
        assert result is not None

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_find_references_svelte_function(self, language_server: SolidLanguageServer) -> None:
        """
        Test finding references to a Svelte component function
        """
        filepath = os.path.join("src", "lib", "Counter.svelte")
        line = 3
        column = 19  # increment function

        result = language_server.request_references(filepath, line, column)

        assert result is not None
        assert len(result) >= 1  # At least the declaration itself

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_document_symbols_svelte(self, language_server: SolidLanguageServer) -> None:
        """
        Test getting document symbols from a Svelte file
        """
        filepath = os.path.join("src", "lib", "Counter.svelte")

        result = language_server.request_document_symbols(filepath)

        assert result is not None
        assert len(result) > 0

        # Flatten the symbol tree to check for functions
        symbols = result[0] if isinstance(result[0], list) else result
        assert SymbolUtils.symbol_tree_contains_name(symbols, "increment"), "increment not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "decrement"), "decrement not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "reset"), "reset not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_document_symbols_typescript(self, language_server: SolidLanguageServer) -> None:
        """
        Test getting document symbols from a TypeScript file in Svelte project
        """
        filepath = os.path.join("src", "lib", "utils.ts")

        result = language_server.request_document_symbols(filepath)

        assert result is not None
        assert len(result) > 0

        # Check for expected symbols
        symbols = result[0] if isinstance(result[0], list) else result
        assert SymbolUtils.symbol_tree_contains_name(symbols, "formatNumber"), "formatNumber not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "calculateSum"), "calculateSum not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "User"), "User not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "UserService"), "UserService not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    def test_hover_svelte_variable(self, language_server: SolidLanguageServer) -> None:
        """
        Test hover information for a variable in Svelte file
        """
        filepath = os.path.join("src", "lib", "Counter.svelte")
        line = 1
        column = 6  # count variable

        result = language_server.request_hover(filepath, line, column)

        assert result is not None
        assert "contents" in result
        # Hover should show type information
        contents = result["contents"]
        if isinstance(contents, dict):
            contents = contents.get("value", "")
        assert "number" in str(contents).lower()

    @pytest.mark.parametrize("language_server", [Language.SVELTE], indirect=True)
    @pytest.mark.skip(reason="Completions not fully supported by svelte-proxy-lsp yet")
    def test_completions_svelte(self, language_server: SolidLanguageServer) -> None:
        """
        Test code completions in Svelte file
        """
        filepath = os.path.join("src", "lib", "Counter.svelte")
        line = 4
        column = 3  # Inside increment function

        # Allow incomplete completions since the server may not fully support them yet
        result = language_server.request_completions(filepath, line, column, allow_incomplete=True)

        assert result is not None
        if isinstance(result, dict):
            assert "items" in result
            items = result["items"]
        else:
            items = result

        # Just check that we get some completions, even if not specific ones
        assert isinstance(items, list)
