import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.cpp
class TestCppLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.CPP], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "main function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Helper"), "Helper function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "DemoStruct"), "DemoStruct not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.CPP], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        # Find references to Helper function by finding a usage in main.cpp
        # This tests cross-file reference resolution: Helper defined in helper.cpp, used in main.cpp
        file_path = os.path.join("main.cpp")

        # Get symbols to ensure both files are indexed
        language_server.request_document_symbols(os.path.join("helper.cpp"))
        symbols = language_server.request_document_symbols(file_path)

        # Find a symbol that calls Helper (UsingHelper function calls Helper)
        using_helper_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "UsingHelper":
                using_helper_symbol = sym
                break
        assert using_helper_symbol is not None, "Could not find 'UsingHelper' function symbol in main.cpp"

        # Find references from within the UsingHelper function (which calls Helper())
        # UsingHelper contains "Helper();" - find references from this call site
        sel_start = using_helper_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"] + 1, 4)  # Next line, at Helper call

        assert any(
            "main.cpp" in ref.get("relativePath", "") for ref in refs
        ), "main.cpp should reference Helper (tried all positions in selectionRange)"
