import os

import pytest
from lsprotocol.types import SymbolKind

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

pytestmark = [pytest.mark.ruby]


class TestRubyLSPLanguageServerSymbols:
    """Test the ruby-lsp language server's symbol-related functionality."""

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_containing_symbol_method(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a method."""
        # Test for a position inside the create_user method
        file_path = os.path.join("services.rb")
        # Look for a position inside the create_user method body
        containing_symbol = language_server.request_containing_symbol(file_path, 11, 10, include_body=True)

        # Verify that we found the containing symbol
        assert containing_symbol is not None, "Should find containing symbol for method position"
        assert containing_symbol["name"] == "create_user", f"Expected 'create_user', got '{containing_symbol['name']}'"
        assert (
            containing_symbol["kind"] == SymbolKind.Method.value
        ), f"Expected Method kind ({SymbolKind.Method.value}), got {containing_symbol['kind']}"

        # Verify location information
        assert "location" in containing_symbol, "Containing symbol should have location information"
        location = containing_symbol["location"]
        assert "range" in location, "Location should contain range information"
        assert "start" in location["range"], "Range should have start position"
        assert "end" in location["range"], "Range should have end position"

        # Verify container information
        if "containerName" in containing_symbol:
            assert containing_symbol["containerName"] in [
                "Services::UserService",
                "UserService",
            ], f"Expected UserService container, got '{containing_symbol['containerName']}'"

        # Verify body content if available
        if "body" in containing_symbol:
            body = containing_symbol["body"]
            assert "def create_user" in body, "Method body should contain method definition"
            assert len(body.strip()) > 0, "Method body should not be empty"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_containing_symbol_class(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a class."""
        # Test for a position inside the UserService class but outside any method
        file_path = os.path.join("services.rb")
        # Line around the class definition
        containing_symbol = language_server.request_containing_symbol(file_path, 5, 5)

        # Verify that we found the containing symbol
        assert containing_symbol is not None, "Should find containing symbol for class position"
        assert containing_symbol["name"] == "UserService", f"Expected 'UserService', got '{containing_symbol['name']}'"
        assert (
            containing_symbol["kind"] == SymbolKind.Class.value
        ), f"Expected Class kind ({SymbolKind.Class.value}), got {containing_symbol['kind']}"

        # Verify location information exists
        assert "location" in containing_symbol, "Class symbol should have location information"
        location = containing_symbol["location"]
        assert "range" in location, "Location should contain range"
        assert "start" in location["range"] and "end" in location["range"], "Range should have start and end positions"

        # Verify the class is properly nested in the Services module
        if "containerName" in containing_symbol:
            assert (
                containing_symbol["containerName"] == "Services"
            ), f"Expected 'Services' as container, got '{containing_symbol['containerName']}'"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_document_symbols_detailed(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols for detailed Ruby file structure."""
        file_path = os.path.join("models.rb")
        symbols, roots = language_server.request_document_symbols(file_path)

        # Verify we have symbols
        assert len(symbols) > 0 or len(roots) > 0

        # Look for expected class names
        symbol_names = set()
        all_symbols = symbols if symbols else roots

        for symbol in all_symbols:
            symbol_names.add(symbol.get("name"))
            # Add children names too
            if "children" in symbol:
                for child in symbol["children"]:
                    symbol_names.add(child.get("name"))

        # We should find at least some of our defined classes/methods
        expected_symbols = {"User", "Item", "Order", "ItemHelpers"}
        found_symbols = symbol_names.intersection(expected_symbols)
        assert len(found_symbols) > 0, f"Expected symbols not found. Found: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_dir_overview(self, language_server: SolidLanguageServer) -> None:
        """Test that request_dir_overview returns correct symbol information for files in a directory."""
        # Get overview of the test repo directory
        overview = language_server.request_dir_overview(".")

        # Verify that we have entries for our main files
        expected_files = ["services.rb", "models.rb", "variables.rb", "nested.rb"]
        found_files = []

        for file_path in overview.keys():
            for expected in expected_files:
                if expected in file_path:
                    found_files.append(expected)
                    break

        assert len(found_files) >= 2, f"Should find at least 2 expected files, found: {found_files}"

        # Test specific symbols from services.rb if it exists
        services_file_key = None
        for file_path in overview.keys():
            if "services.rb" in file_path:
                services_file_key = file_path
                break

        if services_file_key:
            services_symbols = overview[services_file_key]
            assert len(services_symbols) > 0, "services.rb should have symbols"

            # Check for expected symbols with detailed verification
            symbol_names = [s[0] for s in services_symbols if isinstance(s, tuple) and len(s) > 0]
            if not symbol_names:  # If not tuples, try different format
                symbol_names = [s.get("name") for s in services_symbols if hasattr(s, "get")]

            expected_symbols = ["Services", "UserService", "ItemService"]
            found_expected = [name for name in expected_symbols if name in symbol_names]
            assert len(found_expected) >= 1, f"Should find at least one expected symbol, found: {found_expected} in {symbol_names}"
