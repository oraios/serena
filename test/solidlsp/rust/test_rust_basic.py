import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.solidlsp.conftest import has_malformed_name, request_all_symbols


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

    @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s):
                malformed_symbols.append(s)
        assert not malformed_symbols, f"Found malformed symbols: {[sym['name'] for sym in malformed_symbols]}"
