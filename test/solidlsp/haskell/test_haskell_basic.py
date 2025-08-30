"""
Tests for the Haskell language server symbol-related functionality.

These tests focus on the following methods:
- request_containing_symbol
- request_referencing_symbols
- request_defining_symbol
- request_document_symbols integration
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind

pytestmark = pytest.mark.haskell


class TestHaskellLanguageServerSymbols:
    """Test the Haskell language server's symbol-related functionality."""

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_document_symbols_lib_exact_content(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols for Lib.hs and verify exact symbol content."""
        file_path = os.path.join("src", "Lib.hs")

        symbols = language_server.request_document_symbols(file_path)
        assert symbols is not None, "Should receive symbols from HLS"
        assert isinstance(symbols, tuple), f"Expected tuple, got {type(symbols)}"
        assert len(symbols) == 2, f"Expected tuple of length 2, got {len(symbols)}"

        hierarchical_symbols, flat_symbols = symbols

        # Extract symbol names from hierarchical symbols (which should contain the actual functions)
        symbol_names = []
        for symbol in hierarchical_symbols:
            if isinstance(symbol, dict) and "name" in symbol:
                symbol_names.append(symbol["name"])
                # Also check children if they exist
                if symbol.get("children"):
                    for child in symbol["children"]:
                        if isinstance(child, dict) and "name" in child:
                            symbol_names.append(child["name"])

        # Verify exact symbols are present
        expected_symbols = ["add", "hello", "safeDiv", "Calculator", "User", "validateUser"]

        for expected in expected_symbols:
            assert expected in symbol_names, f"Expected symbol '{expected}' not found in symbols: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_document_symbols_main_exact_content(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols for Main.hs."""
        file_path = os.path.join("app", "Main.hs")

        symbols = language_server.request_document_symbols(file_path)
        assert symbols is not None, "Should receive symbols from Main.hs"
        assert isinstance(symbols, tuple), f"Expected tuple, got {type(symbols)}"

        hierarchical_symbols, flat_symbols = symbols

        # Extract symbol names
        symbol_names = []
        for symbol in hierarchical_symbols:
            if isinstance(symbol, dict) and "name" in symbol:
                symbol_names.append(symbol["name"])
                if symbol.get("children"):
                    for child in symbol["children"]:
                        if isinstance(child, dict) and "name" in child:
                            symbol_names.append(child["name"])

        # Main.hs should have a main function
        assert "main" in symbol_names, f"Expected 'main' function, found symbols: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_containing_symbol_function(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a function by using document symbols first."""
        file_path = os.path.join("src", "Lib.hs")

        # First get document symbols to understand the structure
        symbols = language_server.request_document_symbols(file_path)
        assert symbols is not None
        hierarchical_symbols, flat_symbols = symbols

        # Find the add function symbol to get its exact location
        add_symbol = None
        for symbol in hierarchical_symbols:
            if isinstance(symbol, dict) and symbol.get("name") == "add":
                add_symbol = symbol
                break
            if isinstance(symbol, dict) and "children" in symbol:
                for child in symbol["children"]:
                    if isinstance(child, dict) and child.get("name") == "add":
                        add_symbol = child
                        break

        assert add_symbol is not None, "add function symbol not found in document symbols"

        # Get the range of the add function
        assert "range" in add_symbol and "start" in add_symbol["range"], "add function symbol doesn't have range information"

        add_start = add_symbol["range"]["start"]
        test_line = add_start["line"]
        test_char = add_start["character"] + 5  # Position inside function name

        # Test containing symbol
        containing_symbol = language_server.request_containing_symbol(file_path, test_line, test_char, include_body=True)

        assert containing_symbol is not None, "request_containing_symbol returned None - HLS should support this feature"

        # Verify we found the correct symbol
        assert containing_symbol["name"] == "add", f"Expected 'add', got '{containing_symbol.get('name')}'"
        assert containing_symbol["kind"] == SymbolKind.Function.value, f"Expected Function kind, got {containing_symbol.get('kind')}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_containing_symbol_data_type(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for data type by using document symbols first."""
        file_path = os.path.join("src", "Lib.hs")

        # First get document symbols to find Calculator data type
        symbols = language_server.request_document_symbols(file_path)
        assert symbols is not None
        hierarchical_symbols, flat_symbols = symbols

        # Find the Calculator data type symbol
        calculator_symbol = None
        for symbol in hierarchical_symbols:
            if isinstance(symbol, dict) and symbol.get("name") == "Calculator":
                calculator_symbol = symbol
                break
            if isinstance(symbol, dict) and "children" in symbol:
                for child in symbol["children"]:
                    if isinstance(child, dict) and child.get("name") == "Calculator":
                        calculator_symbol = child
                        break

        assert calculator_symbol is not None and "range" in calculator_symbol, "Calculator data type symbol not found or missing range"

        calc_start = calculator_symbol["range"]["start"]
        test_line = calc_start["line"]
        test_char = calc_start["character"] + 5

        containing_symbol = language_server.request_containing_symbol(file_path, test_line, test_char)

        assert containing_symbol is not None, "request_containing_symbol should work for data types"

        assert containing_symbol["name"] == "Calculator", f"Expected 'Calculator', got '{containing_symbol.get('name')}'"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_referencing_symbols_function(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a function."""
        file_path = os.path.join("src", "Lib.hs")

        # Get document symbols first
        symbols = language_server.request_document_symbols(file_path)
        assert symbols is not None
        hierarchical_symbols, flat_symbols = symbols

        # Find add function with selectionRange
        add_symbol = None
        for symbol in hierarchical_symbols:
            if isinstance(symbol, dict) and symbol.get("name") == "add" and "selectionRange" in symbol:
                add_symbol = symbol
                break
            if isinstance(symbol, dict) and "children" in symbol:
                for child in symbol["children"]:
                    if isinstance(child, dict) and child.get("name") == "add" and "selectionRange" in child:
                        add_symbol = child
                        break

        assert add_symbol is not None, "add function with selectionRange not found"

        sel_start = add_symbol["selectionRange"]["start"]
        refs = language_server.request_referencing_symbols(file_path, sel_start["line"], sel_start["character"])

        # refs should be a list of ReferenceWithSymbol objects or similar
        assert isinstance(refs, list), f"Expected list of references, got {type(refs)}"

        # Verify structure if references exist
        for ref in refs:
            if hasattr(ref, "symbol"):
                symbol = ref.symbol
                assert "name" in symbol, "Reference symbol should have name"
                assert "kind" in symbol, "Reference symbol should have kind"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_referencing_symbols_data_type(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a data type."""
        file_path = os.path.join("src", "Lib.hs")

        symbols = language_server.request_document_symbols(file_path)
        assert symbols is not None
        hierarchical_symbols, flat_symbols = symbols

        # Find User data type
        user_symbol = None
        for symbol in hierarchical_symbols:
            if isinstance(symbol, dict) and symbol.get("name") == "User" and "selectionRange" in symbol:
                user_symbol = symbol
                break
            if isinstance(symbol, dict) and "children" in symbol:
                for child in symbol["children"]:
                    if isinstance(child, dict) and child.get("name") == "User" and "selectionRange" in child:
                        user_symbol = child
                        break

        assert user_symbol is not None, "User data type with selectionRange not found"

        sel_start = user_symbol["selectionRange"]["start"]
        refs = language_server.request_referencing_symbols(file_path, sel_start["line"], sel_start["character"])

        assert isinstance(refs, list), f"Expected list of references, got {type(refs)}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_request_defining_symbol_function_usage(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol by looking for function usage in Main.hs."""
        main_file = os.path.join("app", "Main.hs")

        # Look for the add function call in Main.hs (around line 9: print (add 2 3))
        # We'll test position 9, 15 which should be on the 'add' call
        defining_symbol = language_server.request_defining_symbol(main_file, 9, 15)

        assert defining_symbol is not None, "request_defining_symbol should work - go-to-definition is a basic LSP feature"

        # Should find the definition of 'add' function
        assert "name" in defining_symbol, "Defining symbol should have name"
        assert defining_symbol["name"] == "add", f"Expected 'add', got '{defining_symbol.get('name')}'"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_cross_file_references(self, language_server: SolidLanguageServer) -> None:
        """Test that we can find references across files."""
        # The 'add' function is defined in src/Lib.hs and used in app/Main.hs
        src_file = os.path.join("src", "Lib.hs")

        # Get add function location from document symbols
        symbols = language_server.request_document_symbols(src_file)
        assert symbols is not None
        hierarchical_symbols, flat_symbols = symbols

        add_symbol = None
        for symbol in hierarchical_symbols:
            if isinstance(symbol, dict) and symbol.get("name") == "add" and "selectionRange" in symbol:
                add_symbol = symbol
                break
            if isinstance(symbol, dict) and "children" in symbol:
                for child in symbol["children"]:
                    if isinstance(child, dict) and child.get("name") == "add" and "selectionRange" in child:
                        add_symbol = child
                        break

        assert add_symbol is not None, "add function with selectionRange not found for cross-file test"

        sel_start = add_symbol["selectionRange"]["start"]
        refs = language_server.request_referencing_symbols(src_file, sel_start["line"], sel_start["character"])

        assert isinstance(refs, list), f"Expected list of references, got {type(refs)}"

        # Verify structure and content of references - should find the 'add' function
        # The 'add' function is defined in Lib.hs and used in Main.hs
        reference_names = []
        for ref in refs:
            if hasattr(ref, "symbol"):
                symbol = ref.symbol
                assert "name" in symbol, "Reference symbol should have name"
                assert "kind" in symbol, "Reference symbol should have kind"
                reference_names.append(symbol["name"])

        # Cross-file references should include the 'add' function
        assert "add" in reference_names, f"Expected to find 'add' function in references: {reference_names}"
