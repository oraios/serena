import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.haxe
class TestHaxeLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "greet"), "greet function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Helper"), "Helper class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "addNumbers"), "addNumbers function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "User"), "User class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Role"), "Role enum not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "IService"), "IService interface not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "Main.hx")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        greet_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "greet":
                greet_symbol = sym
                break
        assert greet_symbol is not None, "Could not find 'greet' symbol in Main.hx"
        sel_start = greet_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any("Main.hx" in ref.get("relativePath", "") for ref in refs), "Main.hx should reference greet function"

    @pytest.mark.parametrize("language_server", [Language.HAXE], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        # Test formatMessage which is defined in Helper.hx and used in Main.hx and User.hx
        helper_path = os.path.join("src", "util", "Helper.hx")
        symbols = language_server.request_document_symbols(helper_path).get_all_symbols_and_roots()
        format_message_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "formatMessage":
                format_message_symbol = sym
                break
            # Check children (methods inside class)
            for child in sym.get("children", []):
                if child.get("name") == "formatMessage":
                    format_message_symbol = child
                    break
            if format_message_symbol is not None:
                break
        assert format_message_symbol is not None, "Could not find 'formatMessage' symbol in Helper.hx"

        sel_start = format_message_symbol["selectionRange"]["start"]
        refs = language_server.request_references(helper_path, sel_start["line"], sel_start["character"])

        assert refs, "Expected to find references for formatMessage"
        ref_files = {ref.get("relativePath", "") for ref in refs}
        assert any("Main.hx" in f for f in ref_files), "Expected to find usage of formatMessage in Main.hx"
