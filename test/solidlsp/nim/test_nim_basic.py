"""
Tests for the Nim language server implementation.

These tests validate symbol finding and cross-file reference capabilities
for Nim modules and functions.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind


@pytest.mark.nim
class TestNimLanguageServer:
    """Test Nim language server symbol finding and cross-file references."""

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_find_symbols_in_calculator(self, language_server: SolidLanguageServer) -> None:
        """Test finding specific functions in calculator.nim."""
        symbols = language_server.request_document_symbols("src/calculator.nim").get_all_symbols_and_roots()

        assert symbols is not None
        assert len(symbols) > 0

        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        function_names = set()
        for symbol in symbol_list:
            if isinstance(symbol, dict):
                name = symbol.get("name", "")
                if symbol.get("kind") == SymbolKind.Function:
                    function_names.add(name)

        expected_functions = {"add", "subtract", "multiply", "divide", "factorial", "mean"}
        found_functions = function_names & expected_functions
        assert found_functions == expected_functions, f"Expected {expected_functions}, found {found_functions}"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_find_symbols_in_utils(self, language_server: SolidLanguageServer) -> None:
        """Test finding specific functions and types in utils.nim."""
        symbols = language_server.request_document_symbols("src/utils.nim").get_all_symbols_and_roots()

        assert symbols is not None
        assert len(symbols) > 0

        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        function_names = set()
        all_names = set()

        for symbol in symbol_list:
            if isinstance(symbol, dict):
                name = symbol.get("name", "")
                all_names.add(name)
                if symbol.get("kind") == SymbolKind.Function:
                    function_names.add(name)

        expected_utils = {"trim", "split_words", "starts_with", "ends_with", "repeat_string"}
        found_utils = function_names & expected_utils
        assert found_utils == expected_utils, f"Expected {expected_utils}, found {found_utils}"

        # Check for Logger type
        assert "Logger" in all_names or any("Logger" in s for s in all_names), "Logger type not found in symbols"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_find_symbols_in_main(self, language_server: SolidLanguageServer) -> None:
        """Test finding functions in main.nim."""
        symbols = language_server.request_document_symbols("main.nim").get_all_symbols_and_roots()

        assert symbols is not None
        assert len(symbols) > 0

        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        function_names = set()

        for symbol in symbol_list:
            if isinstance(symbol, dict) and symbol.get("kind") == SymbolKind.Function:
                function_names.add(symbol.get("name", ""))

        expected_funcs = {"printBanner", "testCalculator", "testUtils"}
        found_funcs = function_names & expected_funcs
        assert found_funcs == expected_funcs, f"Expected {expected_funcs}, found {found_funcs}"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_cross_file_references_calculator_add(self, language_server: SolidLanguageServer) -> None:
        """Test finding cross-file references to calculator.add function."""
        symbols = language_server.request_document_symbols("src/calculator.nim").get_all_symbols_and_roots()

        assert symbols is not None
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        add_symbol = None
        for sym in symbol_list:
            if isinstance(sym, dict) and sym.get("name") == "add":
                add_symbol = sym
                break

        assert add_symbol is not None, "add function not found in calculator.nim"

        range_info = add_symbol.get("selectionRange", add_symbol.get("range"))
        assert range_info is not None, "add function has no range information"

        range_start = range_info["start"]
        refs = language_server.request_references("src/calculator.nim", range_start["line"], range_start["character"])

        assert refs is not None
        assert isinstance(refs, list)
        assert len(refs) >= 2, f"Should find at least 2 references to add (declaration + usage), found {len(refs)}"

        ref_files: dict[str, list[int]] = {}
        for ref in refs:
            filename = ref.get("uri", "").split("/")[-1]
            if filename not in ref_files:
                ref_files[filename] = []
            ref_files[filename].append(ref["range"]["start"]["line"])

        # main.nim should reference calculator.add
        assert "main.nim" in ref_files, "Should find add usages in main.nim"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_cross_file_references_utils_trim(self, language_server: SolidLanguageServer) -> None:
        """Test finding cross-file references to utils.trim function."""
        symbols = language_server.request_document_symbols("src/utils.nim").get_all_symbols_and_roots()

        assert symbols is not None
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        trim_symbol = None
        for sym in symbol_list:
            if isinstance(sym, dict) and sym.get("name") == "trim":
                trim_symbol = sym
                break

        assert trim_symbol is not None, "trim function not found in utils.nim"

        range_info = trim_symbol.get("selectionRange", trim_symbol.get("range"))
        assert range_info is not None

        range_start = range_info["start"]
        refs = language_server.request_references("src/utils.nim", range_start["line"], range_start["character"])

        assert refs is not None
        assert isinstance(refs, list)
        assert len(refs) >= 1, f"Should find at least 1 reference to trim, found {len(refs)}"

        ref_files: dict[str, list[int]] = {}
        for ref in refs:
            filename = ref.get("uri", "").split("/")[-1]
            if filename not in ref_files:
                ref_files[filename] = []
            ref_files[filename].append(ref["range"]["start"]["line"])

        assert "main.nim" in ref_files, "Should find trim usage in main.nim"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_hover_information(self, language_server: SolidLanguageServer) -> None:
        """Test hover information for symbols."""
        hover_info = language_server.request_hover("src/calculator.nim", 2, 5)

        assert hover_info is not None, "Should provide hover information"

        if isinstance(hover_info, dict):
            assert "contents" in hover_info or "value" in hover_info, "Hover should have contents"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_full_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        """Test that full symbol tree is not empty."""
        symbols = language_server.request_full_symbol_tree()

        assert symbols is not None
        assert len(symbols) > 0, "Symbol tree should not be empty"

        root = symbols[0]
        assert isinstance(root, dict), "Root should be a dict"
        assert "name" in root, "Root should have a name"
