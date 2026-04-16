"""
Tests for the Gleam language server integration.

Test Repository Structure:
    test/resources/repos/gleam/test_repo/
    ├── gleam.toml            # Project manifest (depends on gleam_stdlib)
    └── src/
        ├── calculator.gleam  # Calculator type and arithmetic functions
        └── utils.gleam       # format_output helper used by calculator.gleam
"""

import shutil

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import is_ci
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


@pytest.mark.skipif(shutil.which("gleam") is None and not is_ci, reason="Gleam compiler is not available")
@pytest.mark.gleam
class TestGleamLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.GLEAM], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Symbols defined in the test repo are present in the symbol tree."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "'add' function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "subtract"), "'subtract' function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "multiply"), "'multiply' function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Calculator"), "'Calculator' type not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "format_output"), "'format_output' function not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.GLEAM], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        """References to 'add' inside calculator.gleam are found."""
        file_path = "src/calculator.gleam"
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        add_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "add":
                add_symbol = sym
                break
        assert add_symbol is not None, "Could not find 'add' symbol in calculator.gleam"

        sel_start = add_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert refs, "Expected at least one reference to 'add'"
        assert any("calculator.gleam" in ref.get("relativePath", "") for ref in refs), "Expected a reference to 'add' in calculator.gleam"

    @pytest.mark.parametrize("language_server", [Language.GLEAM], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        """'format_output' defined in utils.gleam is referenced in calculator.gleam."""
        utils_path = "src/utils.gleam"
        symbols = language_server.request_document_symbols(utils_path).get_all_symbols_and_roots()
        format_output_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "format_output":
                format_output_symbol = sym
                break
        assert format_output_symbol is not None, "Could not find 'format_output' symbol in utils.gleam"

        sel_start = format_output_symbol["selectionRange"]["start"]
        refs = language_server.request_references(utils_path, sel_start["line"], sel_start["character"])
        assert refs, "Expected at least one reference to 'format_output'"
        assert any("calculator.gleam" in ref.get("relativePath", "") for ref in refs), (
            "Expected a cross-file reference to 'format_output' in calculator.gleam"
        )

    @pytest.mark.parametrize("language_server", [Language.GLEAM], indirect=True)
    def test_bare_symbol_names(self, language_server: SolidLanguageServer) -> None:
        """No symbol has a malformed name (e.g. path-prefixed or empty)."""
        all_symbols = request_all_symbols(language_server)
        malformed = [s for s in all_symbols if has_malformed_name(s)]
        if malformed:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(s) for s in malformed]}",
                pytrace=False,
            )
