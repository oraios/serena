"""
Basic integration tests for the Crystal language server (Crystalline) functionality.

These tests validate document symbols, go-to-definition, and find-references
using the Crystal test repository.

Known Crystalline limitations:
- Only the first textDocument/definition request per server session returns results.
- textDocument/references is not functional (documented as partial support upstream).
"""

import os
import shutil

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols

pytestmark = [
    pytest.mark.crystal,
    pytest.mark.skipif(shutil.which("crystalline") is None, reason="Crystalline is not installed"),
]


class TestCrystalDocumentSymbols:
    """Test document symbol retrieval, which works reliably in Crystalline."""

    @pytest.mark.parametrize("language_server", [Language.CRYSTAL], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer) -> None:
        """Test that the language server starts successfully."""
        assert language_server.is_running()

    @pytest.mark.parametrize("language_server", [Language.CRYSTAL], indirect=True)
    def test_document_symbols_main(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols are returned for the main file."""
        file_path = os.path.join("src", "main.cr")
        doc_symbols = language_server.request_document_symbols(file_path)
        all_symbols, root_symbols = doc_symbols.get_all_symbols_and_roots()

        symbol_names = [s.get("name") for s in all_symbols if s.get("name")]
        assert "Calculator" in symbol_names, f"Calculator not found in symbols. Found: {symbol_names}"
        assert "User" in symbol_names, f"User not found in symbols. Found: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.CRYSTAL], indirect=True)
    def test_document_symbols_utils(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols are returned for the utils file."""
        file_path = os.path.join("src", "utils.cr")
        doc_symbols = language_server.request_document_symbols(file_path)
        all_symbols, root_symbols = doc_symbols.get_all_symbols_and_roots()

        symbol_names = [s.get("name") for s in all_symbols if s.get("name")]
        assert "Utils" in symbol_names, f"Utils not found in symbols. Found: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.CRYSTAL], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that the full symbol tree contains expected symbols."""
        from solidlsp.ls_utils import SymbolUtils

        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Calculator"), "Calculator not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "User"), "User not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.CRYSTAL], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol names do not contain unexpected formatting characters."""
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )


class TestCrystalDefinition:
    """Test go-to-definition.

    Crystalline only supports one definition request per server session, so
    only a single test is included. A separate test class with its own
    module-scoped ``language_server`` fixture ensures we get a fresh server.
    """

    @pytest.mark.parametrize("language_server", [Language.CRYSTAL], indirect=True)
    def test_goto_definition_within_file(self, language_server: SolidLanguageServer) -> None:
        """Test goto_definition for a symbol defined within the same file."""
        file_path = os.path.join("src", "main.cr")

        # wait for Crystalline to compile the project
        language_server.language_server._wait_for_compilation()

        # Calculator.new on line 35 (0-indexed: 34), col 13 -> Calculator class on line 3 (0-indexed: 2)
        definitions = language_server.request_definition(file_path, 34, 13)
        assert isinstance(definitions, list), "Definitions should be a list"
        assert len(definitions) > 0, "Should find definition for Calculator"

        calculator_def = definitions[0]
        assert calculator_def.get("uri", "").endswith("main.cr"), "Definition should be in main.cr"
        assert calculator_def["range"]["start"]["line"] == 2, "Calculator class should be defined at line 3 (0-indexed: 2)"
