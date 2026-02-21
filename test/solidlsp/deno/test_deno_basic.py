import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.deno
class TestDenoLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.DENO], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "DemoClass"), "DemoClass not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "helperFunction"), "helperFunction not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "printValue"), "printValue method not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.DENO], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("mod.ts")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        helper_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "helperFunction":
                helper_symbol = sym
                break
        assert helper_symbol is not None, "Could not find 'helperFunction' symbol in mod.ts"
        sel_start = helper_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any("mod.ts" in ref.get("relativePath", "") for ref in refs), "mod.ts should reference helperFunction"
        assert any("use_mod.ts" in ref.get("relativePath", "") for ref in refs), "use_mod.ts should reference helperFunction via import"
