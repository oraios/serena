import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import find_identifier_position, get_repo_path, language_has_verified_implementation_support


@pytest.mark.typescript
class TestTypescriptLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.TYPESCRIPT], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "DemoClass"), "DemoClass not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "helperFunction"), "helperFunction not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "printValue"), "printValue method not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.TYPESCRIPT], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("index.ts")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        helper_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "helperFunction":
                helper_symbol = sym
                break
        assert helper_symbol is not None, "Could not find 'helperFunction' symbol in index.ts"
        sel_start = helper_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any("index.ts" in ref.get("relativePath", "") for ref in refs), (
            "index.ts should reference helperFunction (tried all positions in selectionRange)"
        )

    if language_has_verified_implementation_support(Language.TYPESCRIPT):

        @pytest.mark.parametrize("language_server", [Language.TYPESCRIPT], indirect=True)
        def test_find_implementations(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.TYPESCRIPT)
            pos = find_identifier_position(repo_path / "formatters.ts", "formatGreeting")
            assert pos is not None, "Could not find Greeter.formatGreeting in fixture"

            implementations = language_server.request_implementation("formatters.ts", *pos)
            assert implementations, "Expected at least one implementation of Greeter.formatGreeting"
            assert any("formatters.ts" in implementation.get("relativePath", "") for implementation in implementations), (
                f"Expected ConsoleGreeter.formatGreeting in implementations, got: {implementations}"
            )

        @pytest.mark.parametrize("language_server", [Language.TYPESCRIPT], indirect=True)
        def test_request_implementing_symbols(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.TYPESCRIPT)
            pos = find_identifier_position(repo_path / "formatters.ts", "formatGreeting")
            assert pos is not None, "Could not find Greeter.formatGreeting in fixture"

            implementing_symbols = language_server.request_implementing_symbols("formatters.ts", *pos)
            assert implementing_symbols, "Expected implementing symbols for Greeter.formatGreeting"
            assert any(
                symbol.get("name") == "formatGreeting" and "formatters.ts" in symbol["location"].get("relativePath", "")
                for symbol in implementing_symbols
            ), f"Expected ConsoleGreeter.formatGreeting symbol, got: {implementing_symbols}"
