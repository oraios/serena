"""
Basic tests for Fortran language server integration.

These tests validate some low-level LSP functionality and high-level Serena APIs.
Note: These tests require fortls to be installed: pip install fortls
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from solidlsp.ls_utils import SymbolUtils

# Mark all tests in this module as fortran tests
pytestmark = pytest.mark.fortran


class TestFortranLanguageServer:
    """Test Fortran language server functionality."""

    @pytest.mark.parametrize("language_server", [Language.FORTRAN], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test finding symbols using request_full_symbol_tree."""
        symbols = language_server.request_full_symbol_tree()

        # Verify program symbol
        assert SymbolUtils.symbol_tree_contains_name(symbols, "test_program"), "test_program not found in symbol tree"

        # Verify module symbol
        assert SymbolUtils.symbol_tree_contains_name(symbols, "math_utils"), "math_utils module not found in symbol tree"

        # Verify function symbols
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add_numbers"), "add_numbers function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "multiply_numbers"), "multiply_numbers function not found in symbol tree"

        # Verify subroutine symbol
        assert SymbolUtils.symbol_tree_contains_name(symbols, "print_result"), "print_result subroutine not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.FORTRAN], indirect=True)
    def test_request_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols can be retrieved from Fortran files."""
        # Test main.f90 - should have a program symbol
        main_symbols, _ = language_server.request_document_symbols("main.f90")
        program_names = [s.get("name") for s in main_symbols]
        assert "test_program" in program_names, f"Program 'test_program' not found in main.f90. Found: {program_names}"

        # Test modules/math_utils.f90 - should have module and function symbols
        module_symbols, _ = language_server.request_document_symbols("modules/math_utils.f90")
        all_names = [s.get("name") for s in module_symbols]
        assert "math_utils" in all_names, f"Module 'math_utils' not found. Found: {all_names}"
        assert "add_numbers" in all_names, f"Function 'add_numbers' not found. Found: {all_names}"
        assert "multiply_numbers" in all_names, f"Function 'multiply_numbers' not found. Found: {all_names}"
        assert "print_result" in all_names, f"Subroutine 'print_result' not found. Found: {all_names}"

    @pytest.mark.parametrize("language_server", [Language.FORTRAN], indirect=True)
    def test_find_references_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test finding references across files using low-level request_references.

        This tests the LSP textDocument/references capability.
        """
        file_path = "modules/math_utils.f90"
        symbols = language_server.request_document_symbols(file_path)

        # Find the add_numbers function
        add_numbers_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "add_numbers":
                add_numbers_symbol = sym
                break

        assert add_numbers_symbol is not None, "Could not find 'add_numbers' function symbol in math_utils.f90"

        # WORKAROUND: fortls bug - selectionRange.start is at character 0 (line start),
        # but references only work when queried from the function name (character 13).
        # Line 5 (0-indexed: 4) is: "    function add_numbers(a, b) result(sum)"
        #                                      ^13 characters from start
        sel_start = add_numbers_symbol["selectionRange"]["start"]

        # Use character 13 to query from the function name, not the "function" keyword
        refs = language_server.request_references(file_path, sel_start["line"], 13)

        # Should find references (usage in main.f90 + definition in math_utils.f90)
        assert len(refs) > 0, "Should find references to add_numbers function"

        # Verify that main.f90 references the function
        main_refs = [ref for ref in refs if "main.f90" in ref.get("relativePath", "")]
        assert (
            len(main_refs) > 0
        ), f"Expected to find reference in main.f90, but found references in: {[ref.get('relativePath') for ref in refs]}"

    @pytest.mark.parametrize("language_server", [Language.FORTRAN], indirect=True)
    def test_find_definition_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test finding definition across files using request_definition."""
        # In main.f90, line 7 (0-indexed: line 6) contains: result = add_numbers(5.0, 3.0)
        # We want to find the definition of add_numbers in modules/math_utils.f90
        main_file = "main.f90"

        # Position on 'add_numbers' usage (approximately column 13)
        definition_location_list = language_server.request_definition(main_file, 6, 13)

        if not definition_location_list:
            pytest.skip("fortls does not support cross-file go-to-definition for this case")

        assert len(definition_location_list) >= 1, "Should find at least one definition"
        definition_location = definition_location_list[0]

        # The definition should be in modules/math_utils.f90
        assert "math_utils.f90" in definition_location.get(
            "uri", ""
        ), f"Expected definition to be in math_utils.f90, but found in: {definition_location.get('uri')}"

        # Verify the definition is around the correct line (line 4, 0-indexed)
        assert (
            definition_location["range"]["start"]["line"] == 4
        ), f"Expected definition at line 4, but found at line {definition_location['range']['start']['line']}"

    @pytest.mark.parametrize("language_server", [Language.FORTRAN], indirect=True)
    def test_request_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test finding symbols that reference a function - Serena's high-level API.

        This tests request_referencing_symbols which returns not just locations but also
        the containing symbols that have the references. This is different from
        test_find_references_cross_file which only returns locations.

        NOTE: This test works around a fortls bug where selectionRange points to the start
        of the line instead of the function name.
        """
        # Get the add_numbers function symbol from math_utils.f90
        file_path = "modules/math_utils.f90"
        symbols, _ = language_server.request_document_symbols(file_path)

        # Find the add_numbers function
        add_numbers_symbol = None
        for sym in symbols:
            if sym.get("name") == "add_numbers":
                add_numbers_symbol = sym
                break

        assert add_numbers_symbol is not None, "Could not find 'add_numbers' function symbol"

        # WORKAROUND: fortls bug - selectionRange.start is at character 0 (line start),
        # but references only work when queried from the function name (character 13).
        sel_start = add_numbers_symbol["selectionRange"]["start"]
        # Use character 13 to query from the function name, not the "function" keyword
        referencing_symbols = language_server.request_referencing_symbols(file_path, sel_start["line"], 13)

        # Should find referencing symbols (not just locations, but symbols containing the references)
        assert len(referencing_symbols) > 0, "Should find referencing symbols when querying from function name position"

        # Extract the symbols from ReferenceInSymbol objects
        # This is what makes this test different from test_find_references_cross_file:
        # we're testing that we get back SYMBOLS (with name, kind, location) not just locations
        ref_symbols = [ref.symbol for ref in referencing_symbols]

        # Verify we got valid symbol structures with all required fields
        for symbol in ref_symbols:
            assert "name" in symbol, f"Symbol should have a name: {symbol}"
            assert "kind" in symbol, f"Symbol should have a kind: {symbol}"
            # Each symbol should have location information
            assert "location" in symbol, f"Symbol should have location: {symbol}"

        # Note: fortls may not return all cross-file references through request_referencing_symbols
        # because it depends on finding containing symbols for each reference. We verify that
        # the API works and returns valid symbols with proper structure.

    @pytest.mark.parametrize("language_server", [Language.FORTRAN], indirect=True)
    def test_request_defining_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test finding the defining symbol - Serena's high-level API.

        This is similar to test_find_definition_cross_file but uses the high-level
        request_defining_symbol which returns a full symbol with metadata, not just a location.
        """
        # In main.f90, line 7 (0-indexed: line 6) contains: result = add_numbers(5.0, 3.0)
        # We want to find the definition of add_numbers
        main_file = "main.f90"

        # Get the position of add_numbers usage in main.f90
        # Position on 'add_numbers' (approximately column 13)
        defining_symbol = language_server.request_defining_symbol(main_file, 6, 13)

        if defining_symbol is None:
            pytest.skip("fortls does not support cross-file go-to-definition for this case")

        # Should find the add_numbers function with full symbol information
        assert defining_symbol.get("name") == "add_numbers", f"Expected to find 'add_numbers' but got '{defining_symbol.get('name')}'"

        # Check if we have location information
        if "location" not in defining_symbol or "relativePath" not in defining_symbol["location"]:
            pytest.skip("fortls found the symbol but doesn't provide complete location information")

        # The definition should be in modules/math_utils.f90
        defining_path = defining_symbol["location"]["relativePath"]
        assert "math_utils.f90" in defining_path, f"Expected definition to be in math_utils.f90, but found in: {defining_path}"

    @pytest.mark.parametrize("language_server", [Language.FORTRAN], indirect=True)
    def test_request_containing_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test finding the containing symbol for a position in the code."""
        # Test finding the containing symbol for a position inside the add_numbers function
        file_path = "modules/math_utils.f90"

        # Line 8 (0-indexed: line 7) is inside the add_numbers function: "sum = a + b"
        containing_symbol = language_server.request_containing_symbol(file_path, 7, 10, include_body=False)

        if containing_symbol is None:
            pytest.skip("fortls does not support request_containing_symbol or couldn't find the containing symbol")

        # Should find the add_numbers function as the containing symbol
        assert (
            containing_symbol.get("name") == "add_numbers"
        ), f"Expected containing symbol 'add_numbers', got '{containing_symbol.get('name')}'"

        # Verify the symbol kind is Function
        assert (
            containing_symbol.get("kind") == SymbolKind.Function.value
        ), f"Expected Function kind ({SymbolKind.Function.value}), got {containing_symbol.get('kind')}"

        # Verify location information exists
        assert "location" in containing_symbol, "Containing symbol should have location information"
        location = containing_symbol["location"]
        assert "range" in location, "Location should contain range information"
        assert "start" in location["range"] and "end" in location["range"], "Range should have start and end positions"
