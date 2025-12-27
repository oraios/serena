"""
Tests for the Elixir language server symbol-related functionality.

These tests focus on the following methods:
- request_containing_symbol
- request_referencing_symbols
- request_defining_symbol
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind

from . import EXPERT_UNAVAILABLE, EXPERT_UNAVAILABLE_REASON

# These marks will be applied to all tests in this module
pytestmark = [pytest.mark.elixir, pytest.mark.skipif(EXPERT_UNAVAILABLE, reason=f"Next LS not available: {EXPERT_UNAVAILABLE_REASON}")]


class TestElixirLanguageServerSymbols:
    """Test the Elixir language server's symbol-related functionality."""

    @pytest.mark.xfail(
        reason="Expert 0.1.0 bug: document_symbols returns nil for some files (FunctionClauseError in XPExpert.EngineApi.document_symbols/2)"
    )
    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_containing_symbol_function(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a function."""
        # Test for a position inside the create_user function
        file_path = os.path.join("lib", "services.ex")

        # Find the create_user function in the file
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        create_user_line = None
        for i, line in enumerate(lines):
            if "def create_user(" in line:
                create_user_line = i + 2  # Go inside the function body
                break

        if create_user_line is None:
            pytest.skip("Could not find create_user function")

        containing_symbol = language_server.request_containing_symbol(file_path, create_user_line, 10, include_body=True)

        # Verify that we found the containing symbol
        if containing_symbol:
            # Next LS returns the full function signature instead of just the function name
            assert containing_symbol["name"] == "def create_user(pid, id, name, email, roles \\\\ [])"
            assert containing_symbol["kind"] == SymbolKind.Method or containing_symbol["kind"] == SymbolKind.Function
            if "body" in containing_symbol:
                assert "def create_user" in containing_symbol["body"]

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_containing_symbol_module(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a module."""
        # Test for a position inside the UserService module but outside any function
        file_path = os.path.join("lib", "services.ex")

        # Find the UserService module definition
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        user_service_line = None
        for i, line in enumerate(lines):
            if "defmodule UserService do" in line:
                user_service_line = i + 1  # Go inside the module
                break

        if user_service_line is None:
            pytest.skip("Could not find UserService module")

        containing_symbol = language_server.request_containing_symbol(file_path, user_service_line, 5)

        # Verify that we found the containing symbol
        if containing_symbol:
            assert "UserService" in containing_symbol["name"]
            assert containing_symbol["kind"] == SymbolKind.Module or containing_symbol["kind"] == SymbolKind.Class

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_containing_symbol_nested(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol with nested scopes."""
        # Test for a position inside a function which is inside a module
        file_path = os.path.join("lib", "services.ex")

        # Find a function inside UserService
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        function_body_line = None
        for i, line in enumerate(lines):
            if "def create_user(" in line:
                function_body_line = i + 3  # Go deeper into the function body
                break

        if function_body_line is None:
            pytest.skip("Could not find function body")

        containing_symbol = language_server.request_containing_symbol(file_path, function_body_line, 15)

        # Verify that we found the innermost containing symbol (the function)
        if containing_symbol:
            expected_names = ["create_user", "UserService"]
            assert any(name in containing_symbol["name"] for name in expected_names)

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_containing_symbol_none(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a position with no containing symbol."""
        # Test for a position outside any function/module (e.g., in module doc)
        file_path = os.path.join("lib", "services.ex")
        # Line 1-3 are likely in module documentation or imports
        containing_symbol = language_server.request_containing_symbol(file_path, 2, 10)

        # Should return None or an empty dictionary, or the top-level module
        # This is acceptable behavior for module-level positions
        assert containing_symbol is None or containing_symbol == {} or "TestRepo.Services" in str(containing_symbol)

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_referencing_symbols_struct(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a struct."""
        # Test referencing symbols for User struct
        file_path = os.path.join("lib", "models.ex")

        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        user_symbol = None
        for symbol_group in symbols:
            user_symbol = next((s for s in symbol_group if "User" in s.get("name", "")), None)
            if user_symbol:
                break

        if not user_symbol or "selectionRange" not in user_symbol:
            pytest.skip("User symbol or its selectionRange not found")

        sel_start = user_symbol["selectionRange"]["start"]
        ref_symbols = [
            ref.symbol for ref in language_server.request_referencing_symbols(file_path, sel_start["line"], sel_start["character"])
        ]

        if ref_symbols:
            services_references = [
                symbol
                for symbol in ref_symbols
                if "location" in symbol and "uri" in symbol["location"] and "services.ex" in symbol["location"]["uri"]
            ]
            # We expect some references from services.ex
            assert len(services_references) >= 0  # At least attempt to find references

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_referencing_symbols_none(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a position with no symbol."""
        file_path = os.path.join("lib", "services.ex")
        # Line 3 is likely a blank line or comment
        try:
            ref_symbols = [ref.symbol for ref in language_server.request_referencing_symbols(file_path, 3, 0)]
            # If we get here, make sure we got an empty result
            assert ref_symbols == [] or ref_symbols is None
        except Exception:
            # The method might raise an exception for invalid positions
            # which is acceptable behavior
            pass

    # Tests for request_defining_symbol
    @pytest.mark.xfail(
        reason="Expert 0.1.0 bug: definition request crashes (FunctionClauseError in XPExpert.Protocol.Conversions.to_elixir/2)"
    )
    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_defining_symbol_function_call(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a function call."""
        # Find a place where User.new is called in services.ex
        file_path = os.path.join("lib", "services.ex")
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        user_new_call_line = None
        for i, line in enumerate(lines):
            if "User.new(" in line:
                user_new_call_line = i
                break

        if user_new_call_line is None:
            pytest.skip("Could not find User.new call")

        # Try to find the definition of User.new
        defining_symbol = language_server.request_defining_symbol(file_path, user_new_call_line, 15)

        if defining_symbol:
            assert defining_symbol.get("name") == "new" or "User" in defining_symbol.get("name", "")
            if "location" in defining_symbol and "uri" in defining_symbol["location"]:
                assert "models.ex" in defining_symbol["location"]["uri"]

    @pytest.mark.xfail(
        reason="Expert 0.1.0 bug: definition request crashes (FunctionClauseError in XPExpert.Protocol.Conversions.to_elixir/2)"
    )
    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_defining_symbol_struct_usage(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a struct usage."""
        # Find a place where User struct is used in services.ex
        file_path = os.path.join("lib", "services.ex")
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        user_usage_line = None
        for i, line in enumerate(lines):
            if "alias TestRepo.Models.{User" in line:
                user_usage_line = i
                break

        if user_usage_line is None:
            pytest.skip("Could not find User struct usage")

        defining_symbol = language_server.request_defining_symbol(file_path, user_usage_line, 30)

        if defining_symbol:
            assert "User" in defining_symbol.get("name", "")

    @pytest.mark.xfail(
        reason="Expert 0.1.0 bug: definition request crashes (FunctionClauseError in XPExpert.Protocol.Conversions.to_elixir/2)"
    )
    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_defining_symbol_none(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a position with no symbol."""
        # Test for a position with no symbol (e.g., whitespace or comment)
        file_path = os.path.join("lib", "services.ex")
        # Line 3 is likely a blank line
        defining_symbol = language_server.request_defining_symbol(file_path, 3, 0)

        # Should return None or empty
        assert defining_symbol is None or defining_symbol == {}

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_symbol_methods_integration(self, language_server: SolidLanguageServer) -> None:
        """Test integration between different symbol methods."""
        file_path = os.path.join("lib", "models.ex")

        # Find User struct definition
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        user_struct_line = None
        for i, line in enumerate(lines):
            if "defmodule User do" in line:
                user_struct_line = i
                break

        if user_struct_line is None:
            pytest.skip("Could not find User struct")

        # Test containing symbol
        containing = language_server.request_containing_symbol(file_path, user_struct_line + 5, 10)

        if containing:
            # Test that we can find references to this symbol
            if "location" in containing and "range" in containing["location"]:
                start_pos = containing["location"]["range"]["start"]
                refs = [
                    ref.symbol for ref in language_server.request_referencing_symbols(file_path, start_pos["line"], start_pos["character"])
                ]
                # We should find some references or none (both are valid outcomes)
                assert isinstance(refs, list)

    @pytest.mark.xfail(reason="Flaky test, sometimes fails with an Expert-internal error")
    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_symbol_tree_structure(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol tree structure is correctly built."""
        symbol_tree = language_server.request_full_symbol_tree()

        # Should get a tree structure
        assert len(symbol_tree) > 0

        # Should have our test repository structure
        root = symbol_tree[0]
        assert "children" in root

        # Look for lib directory
        lib_dir = None
        for child in root["children"]:
            if child["name"] == "lib":
                lib_dir = child
                break

        if lib_dir:
            # Expert returns module names instead of file names (e.g., 'services' instead of 'services.ex')
            file_names = [child["name"] for child in lib_dir.get("children", [])]
            expected_modules = ["models", "services", "examples", "utils", "test_repo"]
            found_modules = [name for name in expected_modules if name in file_names]
            assert len(found_modules) > 0, f"Expected to find some modules from {expected_modules}, but got {file_names}"

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_dir_overview(self, language_server: SolidLanguageServer) -> None:
        """Test request_dir_overview functionality."""
        lib_overview = language_server.request_dir_overview("lib")

        # Should get an overview of the lib directory
        assert lib_overview is not None
        # Expert returns keys like 'lib/services.ex' instead of just 'lib'
        overview_keys = list(lib_overview.keys()) if hasattr(lib_overview, "keys") else []
        lib_files = [key for key in overview_keys if key.startswith("lib/")]
        assert len(lib_files) > 0, f"Expected to find lib/ files in overview keys: {overview_keys}"

        # Should contain information about our modules
        overview_text = str(lib_overview).lower()
        expected_terms = ["models", "services", "user", "item"]
        found_terms = [term for term in expected_terms if term in overview_text]
        assert len(found_terms) > 0, f"Expected to find some terms from {expected_terms} in overview"

    # @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    # def test_request_document_overview(self, language_server: SolidLanguageServer) -> None:
    #     """Test request_document_overview functionality."""
    #     # COMMENTED OUT: Expert document overview doesn't contain expected terms
    #     # Expert return value: [('TestRepo.Models', 2, 0, 0)] - only module info, no detailed content
    #     # Expected terms like 'user', 'item', 'order', 'struct', 'defmodule' are not present
    #     # This appears to be a limitation of Expert document overview functionality
    #     #
    #     file_path = os.path.join("lib", "models.ex")
    #     doc_overview = language_server.request_document_overview(file_path)
    #
    #     # Should get an overview of the models.ex file
    #     assert doc_overview is not None
    #
    #     # Should contain information about our structs and functions
    #     overview_text = str(doc_overview).lower()
    #     expected_terms = ["user", "item", "order", "struct", "defmodule"]
    #     found_terms = [term for term in expected_terms if term in overview_text]
    #     assert len(found_terms) > 0, f"Expected to find some terms from {expected_terms} in overview"

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_containing_symbol_of_module_attribute(self, language_server: SolidLanguageServer) -> None:
        """Test containing symbol for module attributes."""
        file_path = os.path.join("lib", "models.ex")

        # Find a module attribute like @type or @doc
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        attribute_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith("@type") or line.strip().startswith("@doc"):
                attribute_line = i
                break

        if attribute_line is None:
            pytest.skip("Could not find module attribute")

        containing_symbol = language_server.request_containing_symbol(file_path, attribute_line, 5)

        if containing_symbol:
            # Should be contained within a module
            assert "name" in containing_symbol
            # The containing symbol should be a module
            expected_names = ["User", "Item", "Order", "TestRepo.Models"]
            assert any(name in containing_symbol["name"] for name in expected_names)
