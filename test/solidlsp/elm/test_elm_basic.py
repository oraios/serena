import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.elm
class TestElmLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.ELM], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "greet"), "greet function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "calculateSum"), "calculateSum function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "formatMessage"), "formatMessage function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "addNumbers"), "addNumbers function not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.ELM], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("Main.elm")
        symbols = language_server.request_document_symbols(file_path)
        greet_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "greet":
                greet_symbol = sym
                break
        assert greet_symbol is not None, "Could not find 'greet' symbol in Main.elm"
        sel_start = greet_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any("Main.elm" in ref.get("relativePath", "") for ref in refs), "Main.elm should reference greet function"

    @pytest.mark.parametrize("language_server", [Language.ELM], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        # Test formatMessage function which is defined in Utils.elm and used in Main.elm
        utils_path = os.path.join("Utils.elm")
        symbols = language_server.request_document_symbols(utils_path)
        formatMessage_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "formatMessage":
                formatMessage_symbol = sym
                break
        assert formatMessage_symbol is not None, "Could not find 'formatMessage' symbol in Utils.elm"

        # Get references from the definition in Utils.elm
        sel_start = formatMessage_symbol["selectionRange"]["start"]
        refs = language_server.request_references(utils_path, sel_start["line"], sel_start["character"])

        # Verify that we found references
        assert refs, "Expected to find references for formatMessage"

        # Verify that at least one reference is in Main.elm (where formatMessage is used)
        assert any("Main.elm" in ref.get("relativePath", "") for ref in refs), "Expected to find usage of formatMessage in Main.elm"
