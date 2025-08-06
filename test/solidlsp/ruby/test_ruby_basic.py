import os
from pathlib import Path

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
        print(helper_symbol)
        assert helper_symbol is not None, "Could not find 'helper_function' symbol in main.rb"   

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.RUBY], indirect=True)  
    def test_find_definition_across_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:        
        # Test finding Calculator.add method definition from line 17: Calculator.new.add(demo.value, 10)
        definition_location_list = language_server.request_definition(str(repo_path / "main.rb"), 16,17)  # add method at line 17 (0-indexed 16), position 17
           
        assert len(definition_location_list) == 1
        definition_location = definition_location_list[0]
        print(f"Found definition: {definition_location}")
        assert definition_location["uri"].endswith("lib.rb")
        assert definition_location["range"]["start"]["line"] == 1  # add method on line 2 (0-indexed 1)
