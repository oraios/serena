import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.solidlsp.go import GOPLS_UNAVAILABLE, GOPLS_UNAVAILABLE_REASON


@pytest.mark.go
@pytest.mark.skipif(GOPLS_UNAVAILABLE, reason=f"gopls not available: {GOPLS_UNAVAILABLE_REASON}")
class TestGoLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.GO], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "main function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Helper"), "Helper function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "DemoStruct"), "DemoStruct not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.GO], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("main.go")
        symbols = language_server.request_document_symbols(file_path)
        helper_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "Helper":
                helper_symbol = sym
                break
        assert helper_symbol is not None, "Could not find 'Helper' function symbol in main.go"
        sel_start = helper_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any("main.go" in ref.get("relativePath", "") for ref in refs), (
            "main.go should reference Helper (tried all positions in selectionRange)"
        )
