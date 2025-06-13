import os

import pytest

if os.getenv("RUN_ALL_LS_TESTS") != "1":
    pytest.skip("Skipping non-Python language server tests", allow_module_level=True)

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from multilspy.multilspy_utils import SymbolUtils


@pytest.mark.go
class TestGoLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.GO], indirect=True)
    def test_find_symbol(self, language_server: SyncLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "main function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Helper"), "Helper function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "DemoStruct"), "DemoStruct not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.GO], indirect=True)
    def test_find_referencing_symbols(self, language_server: SyncLanguageServer) -> None:
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
        assert any(
            "main.go" in ref.get("relativePath", "") for ref in refs
        ), "main.go should reference Helper (tried all positions in selectionRange)"
