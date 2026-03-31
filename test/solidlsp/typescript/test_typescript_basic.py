import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


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

    @pytest.mark.parametrize("language_server", [Language.TYPESCRIPT], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s):
                malformed_symbols.append(s)
        assert len(malformed_symbols) == 0, f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}"
