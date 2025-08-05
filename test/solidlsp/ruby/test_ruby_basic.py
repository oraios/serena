import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.ruby
class TestRubyLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "DemoClass"), "DemoClass not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "helper_function"), "helper_function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "print_value"), "print_value not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("main.rb")
        symbols = language_server.request_document_symbols(file_path)
        helper_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "helper_function":
                helper_symbol = sym
                break
        assert helper_symbol is not None, "Could not find 'helper_function' symbol in main.rb"   
