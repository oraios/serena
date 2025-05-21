import os

import pytest

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from multilspy.multilspy_utils import SymbolUtils


@pytest.mark.ocaml
class TestOCamlLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_find_symbol(self, language_server: SyncLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "DemoModule"), "DemoModule not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "fib"), "fib not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "someFunction"), "someFunction function not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.OCAML], indirect=True)
    def test_find_referencing_symbols(self, language_server: SyncLanguageServer) -> None:
        file_path = os.path.join("main.ml")
        symbols = language_server.request_document_symbols(file_path)
        helper_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "fib":
                helper_symbol = sym
                break
        assert helper_symbol is not None, "Could not find 'fib' symbol in main.ml"
        sel_start = helper_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any(
            "main.ml" in ref.get("relativePath", "") for ref in refs
        ), "main.ml should reference fib (tried all positions in selectionRange)"
