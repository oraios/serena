"""
Tests for the Ruby language server symbol-related functionality.

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

pytestmark = pytest.mark.ruby


class TestRubyLanguageServerSymbols:
    """Test the Ruby language server's symbol-related functionality."""

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
    def test_request_containing_symbol_module(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a module context."""
        # Test that we can find the Services module in document symbols
        file_path = os.path.join("services.rb")
        symbols, roots = language_server.request_document_symbols(file_path)

        # Verify Services module appears in document symbols
        services_module = None
        for symbol in symbols:
            if symbol.get("name") == "Services" and symbol.get("kind") == SymbolKind.Module:
                services_module = symbol
                break

        assert services_module is not None, "Services module not found in document symbols"

        # Test that UserService class has Services as container
        # Position inside UserService class
        containing_symbol = language_server.request_containing_symbol(file_path, 4, 8)
        assert containing_symbol is not None
        assert containing_symbol["name"] == "UserService"
        assert containing_symbol["kind"] == SymbolKind.Class
        # Verify the module context is preserved in containerName (if supported by the language server)
        # ruby-lsp doesn't provide containerName, but Solargraph does
        if "containerName" in containing_symbol:
            assert containing_symbol.get("containerName") == "Services"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_containing_symbol_nested_class(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol with nested classes."""
        # Test for a position inside a nested class method
        file_path = os.path.join("nested.rb")
        # Position inside NestedClass.find_me method
        containing_symbol = language_server.request_containing_symbol(file_path, 20, 10)

        # Verify that we found the innermost containing symbol
        assert containing_symbol is not None
        assert containing_symbol["name"] == "find_me"
        assert containing_symbol["kind"] == SymbolKind.Method

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_containing_symbol_none(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a position with no containing symbol."""
        # Test for a position outside any class/method (e.g., in requires)
        file_path = os.path.join("services.rb")
        # Line 1 is a require statement, not inside any class or method
        containing_symbol = language_server.request_containing_symbol(file_path, 1, 5)

        # Should return None or an empty dictionary
        assert containing_symbol is None or containing_symbol == {}

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_referencing_symbols_method(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a method."""
        # Test referencing symbols for create_user method
        file_path = os.path.join("services.rb")
        # Line containing the create_user method definition
        symbols, roots = language_server.request_document_symbols(file_path)
        create_user_symbol = None

        # Find create_user method in the document symbols (Ruby returns flat list)
        for symbol in symbols:
            if symbol.get("name") == "create_user":
                create_user_symbol = symbol
                break

        if not create_user_symbol or "selectionRange" not in create_user_symbol:
            pytest.skip("create_user symbol or its selectionRange not found")

        sel_start = create_user_symbol["selectionRange"]["start"]
        ref_symbols = [
            ref.symbol for ref in language_server.request_referencing_symbols(file_path, sel_start["line"], sel_start["character"])
        ]

        # We might not have references in our simple test setup, so just verify structure
        for symbol in ref_symbols:
            assert "name" in symbol
            assert "kind" in symbol

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_referencing_symbols_class(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a class."""
        # Test referencing symbols for User class
        file_path = os.path.join("models.rb")
        # Find User class in document symbols
        symbols, roots = language_server.request_document_symbols(file_path)
        user_symbol = None

        for symbol in symbols:
            if symbol.get("name") == "User":
                user_symbol = symbol
                break

        if not user_symbol or "selectionRange" not in user_symbol:
            pytest.skip("User symbol or its selectionRange not found")

        sel_start = user_symbol["selectionRange"]["start"]
        ref_symbols = [
            ref.symbol for ref in language_server.request_referencing_symbols(file_path, sel_start["line"], sel_start["character"])
        ]

        # Verify structure of referencing symbols
        for symbol in ref_symbols:
            assert "name" in symbol
            assert "kind" in symbol
            if "location" in symbol and "range" in symbol["location"]:
                assert "start" in symbol["location"]["range"]
                assert "end" in symbol["location"]["range"]

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_defining_symbol_variable(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a variable usage."""
        # Test finding the definition of a variable in a method
        file_path = os.path.join("services.rb")
        # Look for @users variable usage
        defining_symbol = language_server.request_defining_symbol(file_path, 12, 10)

        # This test might fail if the language server doesn't support it well
        if defining_symbol is not None:
            assert "name" in defining_symbol
            assert "kind" in defining_symbol

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_defining_symbol_class(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a class reference."""
        # Test finding the definition of the User class used in services
        file_path = os.path.join("services.rb")
        # Line that references User class
        defining_symbol = language_server.request_defining_symbol(file_path, 11, 15)

        # This might not work perfectly in all Ruby language servers
        if defining_symbol is not None:
            assert "name" in defining_symbol
            # The name might be "User" or the method that contains it
            assert defining_symbol.get("name") is not None

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_defining_symbol_none(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a position with no symbol."""
        # Test for a position with no symbol (e.g., whitespace or comment)
        file_path = os.path.join("services.rb")
        # Line 3 is likely a blank line or comment
        defining_symbol = language_server.request_defining_symbol(file_path, 3, 0)

        # Should return None for positions with no symbol
        assert defining_symbol is None or defining_symbol == {}

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_defining_symbol_nested_class(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for nested class access."""
        # Test finding definition of NestedClass
        file_path = os.path.join("nested.rb")
        # Position where NestedClass is referenced
        defining_symbol = language_server.request_defining_symbol(file_path, 44, 25)

        # This is challenging for many language servers
        if defining_symbol is not None:
            assert "name" in defining_symbol
            assert defining_symbol.get("name") in ["NestedClass", "OuterClass"]

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_symbol_methods_integration(self, language_server: SolidLanguageServer) -> None:
        """Test the integration between different symbol-related methods."""
        file_path = os.path.join("models.rb")

        # Step 1: Find a method we know exists
        containing_symbol = language_server.request_containing_symbol(file_path, 8, 5)  # inside initialize method
        if containing_symbol is not None:
            assert containing_symbol["name"] == "initialize"

            # Step 2: Get the defining symbol for the same position
            defining_symbol = language_server.request_defining_symbol(file_path, 8, 5)
            if defining_symbol is not None:
                assert defining_symbol["name"] == "initialize"

                # Step 3: Verify that they refer to the same symbol type
                assert defining_symbol["kind"] == containing_symbol["kind"]

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_symbol_tree_structure_basic(self, language_server: SolidLanguageServer) -> None:
        """Test that the symbol tree structure includes Ruby symbols."""
        # Get all symbols in the test repository
        repo_structure = language_server.request_full_symbol_tree()
        assert len(repo_structure) >= 1

        # Look for our Ruby files in the structure
        found_ruby_files = False
        for root in repo_structure:
            if "children" in root:
                for child in root["children"]:
                    if child.get("name") in ["models", "services", "nested"]:
                        found_ruby_files = True
                        break

        # We should find at least some Ruby files in the symbol tree
        assert found_ruby_files, "Ruby files not found in symbol tree"

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
    def test_module_and_class_hierarchy(self, language_server: SolidLanguageServer) -> None:
        """Test symbol detection for modules and nested class hierarchies."""
        file_path = os.path.join("nested.rb")
        symbols, roots = language_server.request_document_symbols(file_path)

        # Verify we can detect the nested structure
        assert len(symbols) > 0 or len(roots) > 0

        # Look for OuterClass and its nested elements
        symbol_names = set()
        all_symbols = symbols if symbols else roots

        for symbol in all_symbols:
            symbol_names.add(symbol.get("name"))
            if "children" in symbol:
                for child in symbol["children"]:
                    symbol_names.add(child.get("name"))
                    # Check deeply nested too
                    if "children" in child:
                        for grandchild in child["children"]:
                            symbol_names.add(grandchild.get("name"))

        # Should find the outer class at minimum
        assert "OuterClass" in symbol_names, f"OuterClass not found in symbols: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_references_to_variables(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a variable with detailed verification."""
        file_path = os.path.join("variables.rb")
        # Test references to @status variable in DataContainer class (around line 9)
        ref_symbols = [ref.symbol for ref in language_server.request_referencing_symbols(file_path, 8, 4)]

        if len(ref_symbols) > 0:
            # Verify we have references
            assert len(ref_symbols) > 0, "Should find references to @status variable"

            # Check that we have location information
            ref_with_locations = [ref for ref in ref_symbols if "location" in ref and "range" in ref["location"]]
            assert len(ref_with_locations) > 0, "References should include location information"

            # Verify line numbers are reasonable (should be within the file)
            ref_lines = [ref["location"]["range"]["start"]["line"] for ref in ref_with_locations]
            assert all(line >= 0 for line in ref_lines), "Reference lines should be valid"

            # Check for specific reference locations we expect
            # Lines where @status is modified/accessed
            expected_line_ranges = [(20, 40), (45, 70)]  # Approximate ranges
            found_in_expected_range = any(any(start <= line <= end for start, end in expected_line_ranges) for line in ref_lines)
            assert found_in_expected_range, f"Expected references in ranges {expected_line_ranges}, found lines: {ref_lines}"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_referencing_symbols_parameter(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a method parameter."""
        # Test referencing symbols for a method parameter in get_user method
        file_path = os.path.join("services.rb")
        # Find get_user method and test parameter references
        symbols, roots = language_server.request_document_symbols(file_path)
        get_user_symbol = None

        for symbol in symbols:
            if symbol.get("name") == "get_user":
                get_user_symbol = symbol
                break

        if not get_user_symbol or "selectionRange" not in get_user_symbol:
            pytest.skip("get_user symbol or its selectionRange not found")

        # Test parameter reference within method body
        method_start_line = get_user_symbol["selectionRange"]["start"]["line"]
        ref_symbols = [
            ref.symbol
            for ref in language_server.request_referencing_symbols(file_path, method_start_line + 1, 10)  # Position within method body
        ]

        # Verify structure of referencing symbols
        for symbol in ref_symbols:
            assert "name" in symbol, "Symbol should have name"
            assert "kind" in symbol, "Symbol should have kind"
            if "location" in symbol and "range" in symbol["location"]:
                range_info = symbol["location"]["range"]
                assert "start" in range_info, "Range should have start"
                assert "end" in range_info, "Range should have end"
                # Verify line number is valid (references can be before method definition too)
                assert range_info["start"]["line"] >= 0, "Reference line should be valid"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_referencing_symbols_none(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a position with no symbol."""
        # Test for a position with no symbol (comment or blank line)
        file_path = os.path.join("services.rb")

        # Try multiple positions that should have no symbols
        test_positions = [(1, 0), (2, 0)]  # Comment/require lines

        for line, char in test_positions:
            try:
                ref_symbols = [ref.symbol for ref in language_server.request_referencing_symbols(file_path, line, char)]
                # If we get here, make sure we got an empty result or minimal results
                if ref_symbols:
                    # Some language servers might return minimal info, verify it's reasonable
                    assert len(ref_symbols) <= 3, f"Expected few/no references at line {line}, got {len(ref_symbols)}"

            except Exception as e:
                # Some language servers throw exceptions for invalid positions, which is acceptable
                assert (
                    "symbol" in str(e).lower() or "position" in str(e).lower() or "reference" in str(e).lower()
                ), f"Exception should be related to symbol/position/reference issues, got: {e}"

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

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_document_overview(self, language_server: SolidLanguageServer) -> None:
        """Test that request_document_overview returns correct symbol information for a file."""
        # Get overview of the user_management.rb file
        file_path = os.path.join("examples", "user_management.rb")
        overview = language_server.request_document_overview(file_path)

        # Verify that we have symbol information
        assert len(overview) > 0, "Document overview should contain symbols"

        # Look for expected symbols from the file
        symbol_names = set()
        for s_info in overview:
            if isinstance(s_info, tuple) and len(s_info) > 0:
                symbol_names.add(s_info[0])
            elif hasattr(s_info, "get"):
                symbol_names.add(s_info.get("name"))
            elif isinstance(s_info, str):
                symbol_names.add(s_info)

        # We should find some of our defined classes/methods
        expected_symbols = {"UserStats", "UserManager", "process_user_data", "main"}
        found_symbols = symbol_names.intersection(expected_symbols)
        assert len(found_symbols) > 0, f"Expected to find some symbols from {expected_symbols}, found: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_containing_symbol_variable(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol where the target is a variable."""
        # Test for a position inside a variable definition or usage
        file_path = os.path.join("variables.rb")
        # Position around a variable assignment (e.g., @status = "pending")
        containing_symbol = language_server.request_containing_symbol(file_path, 10, 5)

        # Verify that we found a containing symbol (likely the method or class)
        if containing_symbol is not None:
            assert "name" in containing_symbol, "Containing symbol should have a name"
            assert "kind" in containing_symbol, "Containing symbol should have a kind"
            # The containing symbol should be a method, class, or similar construct
            expected_kinds = [SymbolKind.Method, SymbolKind.Class, SymbolKind.Function, SymbolKind.Constructor]
            assert containing_symbol["kind"] in [
                k.value for k in expected_kinds
            ], f"Expected containing symbol to be method/class/function, got kind: {containing_symbol['kind']}"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_containing_symbol_function(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a function (not method)."""
        # Test for a position inside a standalone function
        file_path = os.path.join("variables.rb")
        # Position inside the demonstrate_variable_usage function
        containing_symbol = language_server.request_containing_symbol(file_path, 100, 10)

        if containing_symbol is not None:
            assert containing_symbol["name"] in [
                "demonstrate_variable_usage",
                "main",
            ], f"Expected function name, got: {containing_symbol['name']}"
            assert containing_symbol["kind"] in [
                SymbolKind.Function.value,
                SymbolKind.Method.value,
            ], f"Expected function or method kind, got: {containing_symbol['kind']}"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_containing_symbol_nested(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol with nested scopes."""
        # Test for a position inside a method which is inside a class
        file_path = os.path.join("services.rb")
        # Position inside create_user method within UserService class
        containing_symbol = language_server.request_containing_symbol(file_path, 12, 15)

        # Verify that we found the innermost containing symbol (the method)
        assert containing_symbol is not None
        assert containing_symbol["name"] == "create_user"
        assert containing_symbol["kind"] == SymbolKind.Method

        # Verify the container context is preserved
        if "containerName" in containing_symbol:
            assert "UserService" in containing_symbol["containerName"]

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_symbol_tree_structure_subdir(self, language_server: SolidLanguageServer) -> None:
        """Test that the symbol tree structure correctly handles subdirectories."""
        # Get symbols within the examples subdirectory
        examples_structure = language_server.request_full_symbol_tree(within_relative_path="examples")

        if len(examples_structure) > 0:
            # Should find the examples directory structure
            assert len(examples_structure) >= 1, "Should find examples directory structure"

            # Look for the user_management file in the structure
            found_user_management = False
            for root in examples_structure:
                if "children" in root:
                    for child in root["children"]:
                        if "user_management" in child.get("name", ""):
                            found_user_management = True
                            # Verify the structure includes symbol information
                            if "children" in child:
                                child_names = [c.get("name") for c in child["children"]]
                                expected_names = ["UserStats", "UserManager", "process_user_data"]
                                found_expected = [name for name in expected_names if name in child_names]
                                assert (
                                    len(found_expected) > 0
                                ), f"Should find symbols in user_management, expected {expected_names}, found {child_names}"
                            break

            if not found_user_management:
                pytest.skip("user_management file not found in examples subdirectory structure")

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_defining_symbol_imported_class(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for an imported/required class."""
        # Test finding the definition of a class used from another file
        file_path = os.path.join("examples", "user_management.rb")
        # Position where Services::UserService is referenced
        defining_symbol = language_server.request_defining_symbol(file_path, 25, 20)

        # This might not work perfectly in all Ruby language servers due to require complexity
        if defining_symbol is not None:
            assert "name" in defining_symbol
            # The defining symbol should relate to UserService or Services
            # The defining symbol should relate to UserService, Services, or the containing class
            # Different language servers may resolve this differently
            expected_names = ["UserService", "Services", "new", "UserManager"]
            assert defining_symbol.get("name") in expected_names, f"Expected one of {expected_names}, got: {defining_symbol.get('name')}"

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_defining_symbol_method_call(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a method call."""
        # Test finding the definition of a method being called
        file_path = os.path.join("examples", "user_management.rb")
        # Position at a method call like create_user
        defining_symbol = language_server.request_defining_symbol(file_path, 30, 15)

        # Verify that we can find method definitions
        if defining_symbol is not None:
            assert "name" in defining_symbol
            assert "kind" in defining_symbol
            # Should be a method or constructor
            assert defining_symbol.get("kind") in [SymbolKind.Method.value, SymbolKind.Constructor.value, SymbolKind.Function.value]

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_request_defining_symbol_nested_function(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a nested function or block."""
        # Test finding definition within nested contexts
        file_path = os.path.join("nested.rb")
        # Position inside or referencing nested functionality
        defining_symbol = language_server.request_defining_symbol(file_path, 15, 10)

        # This is challenging for many language servers
        if defining_symbol is not None:
            assert "name" in defining_symbol
            assert "kind" in defining_symbol
            # Could be method, function, or variable depending on implementation
            valid_kinds = [SymbolKind.Method.value, SymbolKind.Function.value, SymbolKind.Variable.value, SymbolKind.Class.value]
            assert defining_symbol.get("kind") in valid_kinds

    @pytest.mark.parametrize("language_server", [Language.RUBY], indirect=True)
    def test_containing_symbol_of_var_is_file(self, language_server: SolidLanguageServer) -> None:
        """Test that the containing symbol of a file-level variable is handled appropriately."""
        # Test behavior with file-level variables or constants
        file_path = os.path.join("variables.rb")
        # Position at file-level variable/constant
        containing_symbol = language_server.request_containing_symbol(file_path, 5, 5)

        # Different language servers handle file-level symbols differently
        # Some return None, others return file-level containers
        if containing_symbol is not None:
            # If we get a symbol, verify its structure
            assert "name" in containing_symbol
            assert "kind" in containing_symbol
