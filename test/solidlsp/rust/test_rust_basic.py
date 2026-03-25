import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import find_identifier_position, get_repo_path, language_has_verified_implementation_support


@pytest.mark.rust
class TestRustLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
    def test_find_references_raw(self, language_server: SolidLanguageServer) -> None:
        # Directly test the request_references method for the add function
        file_path = os.path.join("src", "lib.rs")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        add_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "add":
                add_symbol = sym
                break
        assert add_symbol is not None, "Could not find 'add' function symbol in lib.rs"
        sel_start = add_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any("main.rs" in ref.get("relativePath", "") for ref in refs), (
            "main.rs should reference add (raw, tried all positions in selectionRange)"
        )

    @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "main function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "add function not found in symbol tree"
        # Add more as needed based on test_repo

    @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        # Find references to 'add' defined in lib.rs, should be referenced from main.rs
        file_path = os.path.join("src", "lib.rs")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        add_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "add":
                add_symbol = sym
                break
        assert add_symbol is not None, "Could not find 'add' function symbol in lib.rs"
        sel_start = add_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any("main.rs" in ref.get("relativePath", "") for ref in refs), (
            "main.rs should reference add (tried all positions in selectionRange)"
        )

    @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
    def test_overview_methods(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "main missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "add missing from overview"

    if language_has_verified_implementation_support(Language.RUST):

        @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
        def test_find_implementations(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.RUST)
            pos = find_identifier_position(repo_path / os.path.join("src", "lib.rs"), "format_greeting")
            assert pos is not None, "Could not find Greeter.format_greeting in fixture"

            implementations = language_server.request_implementation(os.path.join("src", "lib.rs"), *pos)
            assert implementations, "Expected at least one implementation of Greeter.format_greeting"
            assert any("src\\lib.rs" in implementation.get("relativePath", "") for implementation in implementations), (
                f"Expected ConsoleGreeter.format_greeting in implementations, got: {implementations}"
            )

        @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
        def test_request_implementing_symbols(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.RUST)
            pos = find_identifier_position(repo_path / os.path.join("src", "lib.rs"), "format_greeting")
            assert pos is not None, "Could not find Greeter.format_greeting in fixture"

            implementing_symbols = language_server.request_implementing_symbols(os.path.join("src", "lib.rs"), *pos)
            assert implementing_symbols, "Expected implementing symbols for Greeter.format_greeting"
            assert any(
                symbol.get("name") == "format_greeting" and "src\\lib.rs" in symbol["location"].get("relativePath", "")
                for symbol in implementing_symbols
            ), f"Expected ConsoleGreeter.format_greeting symbol, got: {implementing_symbols}"
