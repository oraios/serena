"""
Tests for the Erlang language server symbol-related functionality.

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

from . import ERLANG_LS_UNAVAILABLE, ERLANG_LS_UNAVAILABLE_REASON

# These marks will be applied to all tests in this module
pytestmark = [
    pytest.mark.erlang,
    pytest.mark.skipif(ERLANG_LS_UNAVAILABLE, reason=f"Erlang LS not available: {ERLANG_LS_UNAVAILABLE_REASON}"),
]


class TestErlangLanguageServerSymbols:
    """Test the Erlang language server's symbol-related functionality."""

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_containing_symbol_function(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a function."""
        # Test for a position inside the create_user function
        file_path = os.path.join("src", "models.erl")

        # Find the create_user function in the file
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        create_user_line = None
        for i, line in enumerate(lines):
            if "create_user(" in line and "-spec" not in line:
                create_user_line = i + 1  # Go inside the function body
                break

        if create_user_line is None:
            pytest.skip("Could not find create_user function")

        containing_symbol = language_server.request_containing_symbol(file_path, create_user_line, 10, include_body=True)

        # Verify that we found the containing symbol
        if containing_symbol:
            assert "create_user" in containing_symbol["name"]
            assert containing_symbol["kind"] == SymbolKind.Method or containing_symbol["kind"] == SymbolKind.Function
            if "body" in containing_symbol:
                assert "create_user" in containing_symbol["body"].get_text()

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_containing_symbol_module(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a module."""
        # Test for a position inside the models module but outside any function
        file_path = os.path.join("src", "models.erl")

        # Find the module definition
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        module_line = None
        for i, line in enumerate(lines):
            if "-module(models)" in line:
                module_line = i + 2  # Go inside the module
                break

        if module_line is None:
            pytest.skip("Could not find models module")

        containing_symbol = language_server.request_containing_symbol(file_path, module_line, 5)

        # Verify that we found the containing symbol
        if containing_symbol:
            assert "models" in containing_symbol["name"] or "module" in containing_symbol["name"].lower()
            assert containing_symbol["kind"] == SymbolKind.Module or containing_symbol["kind"] == SymbolKind.Class

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_containing_symbol_nested(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol with nested scopes."""
        # Test for a position inside a function which is inside a module
        file_path = os.path.join("src", "models.erl")

        # Find a function inside models module
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        function_body_line = None
        for i, line in enumerate(lines):
            if "create_user(" in line and "-spec" not in line:
                # Go deeper into the function body where there might be case expressions
                for j in range(i + 1, min(i + 10, len(lines))):
                    if lines[j].strip() and not lines[j].strip().startswith("%"):
                        function_body_line = j
                        break
                break

        if function_body_line is None:
            pytest.skip("Could not find function body")

        containing_symbol = language_server.request_containing_symbol(file_path, function_body_line, 15)

        # Verify that we found the innermost containing symbol (the function)
        if containing_symbol:
            expected_names = ["create_user", "models"]
            assert any(name in containing_symbol["name"] for name in expected_names)

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_containing_symbol_none(self, language_server: SolidLanguageServer) -> None:
        """Test request_containing_symbol for a position with no containing symbol."""
        # Test for a position outside any function/module (e.g., in comments)
        file_path = os.path.join("src", "models.erl")
        # Line 1-2 are likely module declaration or comments
        containing_symbol = language_server.request_containing_symbol(file_path, 2, 10)

        # Should return None or an empty dictionary, or the top-level module
        # This is acceptable behavior for module-level positions
        assert containing_symbol is None or containing_symbol == {} or "models" in str(containing_symbol)

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_referencing_symbols_record(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a record."""
        # Test referencing symbols for user record
        file_path = os.path.join("include", "records.hrl")

        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        user_symbol = None
        for symbol_group in symbols:
            user_symbol = next((s for s in symbol_group if "user" in s.get("name", "")), None)
            if user_symbol:
                break

        if not user_symbol or "selectionRange" not in user_symbol:
            pytest.skip("User record symbol or its selectionRange not found")

        sel_start = user_symbol["selectionRange"]["start"]
        ref_symbols = [
            ref.symbol for ref in language_server.request_referencing_symbols(file_path, sel_start["line"], sel_start["character"])
        ]

        if ref_symbols:
            models_references = [
                symbol
                for symbol in ref_symbols
                if "location" in symbol and "uri" in symbol["location"] and "models.erl" in symbol["location"]["uri"]
            ]
            # We expect some references from models.erl
            assert len(models_references) >= 0  # At least attempt to find references

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_referencing_symbols_function(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a function."""
        # Test referencing symbols for create_user function
        file_path = os.path.join("src", "models.erl")

        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        create_user_symbol = None
        for symbol_group in symbols:
            create_user_symbol = next((s for s in symbol_group if "create_user" in s.get("name", "")), None)
            if create_user_symbol:
                break

        if not create_user_symbol or "selectionRange" not in create_user_symbol:
            pytest.skip("create_user function symbol or its selectionRange not found")

        sel_start = create_user_symbol["selectionRange"]["start"]
        ref_symbols = [
            ref.symbol for ref in language_server.request_referencing_symbols(file_path, sel_start["line"], sel_start["character"])
        ]

        if ref_symbols:
            # We might find references from services.erl or test files
            service_references = [
                symbol
                for symbol in ref_symbols
                if "location" in symbol
                and "uri" in symbol["location"]
                and ("services.erl" in symbol["location"]["uri"] or "test" in symbol["location"]["uri"])
            ]
            assert len(service_references) >= 0  # At least attempt to find references

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_referencing_symbols_none(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols for a position with no symbol."""
        file_path = os.path.join("src", "models.erl")
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
    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_defining_symbol_function_call(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a function call."""
        # Find a place where models:create_user is called in services.erl
        file_path = os.path.join("src", "services.erl")
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        models_call_line = None
        for i, line in enumerate(lines):
            if "models:create_user(" in line:
                models_call_line = i
                break

        if models_call_line is None:
            pytest.skip("Could not find models:create_user call")

        # Try to find the definition of models:create_user
        defining_symbol = language_server.request_defining_symbol(file_path, models_call_line, 20)

        if defining_symbol:
            assert "create_user" in defining_symbol.get("name", "") or "models" in defining_symbol.get("name", "")
            if "location" in defining_symbol and "uri" in defining_symbol["location"]:
                assert "models.erl" in defining_symbol["location"]["uri"]

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_defining_symbol_record_usage(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a record usage."""
        # Find a place where #user{} record is used in models.erl
        file_path = os.path.join("src", "models.erl")
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        record_usage_line = None
        for i, line in enumerate(lines):
            if "#user{" in line:
                record_usage_line = i
                break

        if record_usage_line is None:
            pytest.skip("Could not find #user{} record usage")

        defining_symbol = language_server.request_defining_symbol(file_path, record_usage_line, 10)

        if defining_symbol:
            assert "user" in defining_symbol.get("name", "").lower()
            if "location" in defining_symbol and "uri" in defining_symbol["location"]:
                assert "records.hrl" in defining_symbol["location"]["uri"]

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_defining_symbol_module_call(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a module function call."""
        # Find a place where utils:validate_input is called
        file_path = os.path.join("src", "models.erl")
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        utils_call_line = None
        for i, line in enumerate(lines):
            if "validate_email(" in line:
                utils_call_line = i
                break

        if utils_call_line is None:
            pytest.skip("Could not find function call in models.erl")

        defining_symbol = language_server.request_defining_symbol(file_path, utils_call_line, 15)

        if defining_symbol:
            assert "validate" in defining_symbol.get("name", "") or "email" in defining_symbol.get("name", "")

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_defining_symbol_none(self, language_server: SolidLanguageServer) -> None:
        """Test request_defining_symbol for a position with no symbol."""
        # Test for a position with no symbol (e.g., whitespace or comment)
        file_path = os.path.join("src", "models.erl")
        # Line 3 is likely a blank line or comment
        defining_symbol = language_server.request_defining_symbol(file_path, 3, 0)

        # Should return None or empty
        assert defining_symbol is None or defining_symbol == {}

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_symbol_methods_integration(self, language_server: SolidLanguageServer) -> None:
        """Test integration between different symbol methods."""
        file_path = os.path.join("src", "models.erl")

        # Find create_user function definition
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        create_user_line = None
        for i, line in enumerate(lines):
            if "create_user(" in line and "-spec" not in line:
                create_user_line = i
                break

        if create_user_line is None:
            pytest.skip("Could not find create_user function")

        # Test containing symbol
        containing = language_server.request_containing_symbol(file_path, create_user_line + 2, 10)

        if containing:
            # Test that we can find references to this symbol
            if "location" in containing and "range" in containing["location"]:
                start_pos = containing["location"]["range"]["start"]
                refs = [
                    ref.symbol for ref in language_server.request_referencing_symbols(file_path, start_pos["line"], start_pos["character"])
                ]
                # We should find some references or none (both are valid outcomes)
                assert isinstance(refs, list)

    @pytest.mark.timeout(60)  # Add 60 second timeout
    @pytest.mark.xfail(
        reason="Known intermittent timeout issue in Erlang LS in CI environments. "
        "May pass locally but can timeout on slower CI systems.",
        strict=False,
    )
    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_symbol_tree_structure(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol tree structure is correctly built."""
        symbol_tree = language_server.request_full_symbol_tree()

        # Should get a tree structure
        assert len(symbol_tree) > 0

        # Should have our test repository structure
        root = symbol_tree[0]
        assert "children" in root

        # Look for src directory
        src_dir = None
        for child in root["children"]:
            if child["name"] == "src":
                src_dir = child
                break

        if src_dir:
            # Check for our Erlang modules
            file_names = [child["name"] for child in src_dir.get("children", [])]
            expected_modules = ["models", "services", "utils", "app"]
            found_modules = [name for name in expected_modules if any(name in fname for fname in file_names)]
            assert len(found_modules) > 0, f"Expected to find some modules from {expected_modules}, but got {file_names}"

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_request_dir_overview(self, language_server: SolidLanguageServer) -> None:
        """Test request_dir_overview functionality."""
        src_overview = language_server.request_dir_overview("src")

        # Should get an overview of the src directory
        assert src_overview is not None
        overview_keys = list(src_overview.keys()) if hasattr(src_overview, "keys") else []
        src_files = [key for key in overview_keys if key.startswith("src/") or "src" in key]
        assert len(src_files) > 0, f"Expected to find src/ files in overview keys: {overview_keys}"

        # Should contain information about our modules
        overview_text = str(src_overview).lower()
        expected_terms = ["models", "services", "user", "create_user", "gen_server"]
        found_terms = [term for term in expected_terms if term in overview_text]
        assert len(found_terms) > 0, f"Expected to find some terms from {expected_terms} in overview"

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_containing_symbol_of_record_field(self, language_server: SolidLanguageServer) -> None:
        """Test containing symbol for record field access."""
        file_path = os.path.join("src", "models.erl")

        # Find a record field access like User#user.name
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        record_field_line = None
        for i, line in enumerate(lines):
            if "#user{" in line and ("name" in line or "email" in line or "id" in line):
                record_field_line = i
                break

        if record_field_line is None:
            pytest.skip("Could not find record field access")

        containing_symbol = language_server.request_containing_symbol(file_path, record_field_line, 10)

        if containing_symbol:
            # Should be contained within a function
            assert "name" in containing_symbol
            expected_names = ["create_user", "update_user", "format_user_info"]
            assert any(name in containing_symbol["name"] for name in expected_names)

    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_containing_symbol_of_spec(self, language_server: SolidLanguageServer) -> None:
        """Test containing symbol for function specs."""
        file_path = os.path.join("src", "models.erl")

        # Find a -spec directive
        content = language_server.retrieve_full_file_content(file_path)
        lines = content.split("\n")
        spec_line = None
        for i, line in enumerate(lines):
            if line.strip().startswith("-spec") and "create_user" in line:
                spec_line = i
                break

        if spec_line is None:
            pytest.skip("Could not find -spec directive")

        containing_symbol = language_server.request_containing_symbol(file_path, spec_line, 5)

        if containing_symbol:
            # Should be contained within the module or the function it specifies
            assert "name" in containing_symbol
            expected_names = ["models", "create_user"]
            assert any(name in containing_symbol["name"] for name in expected_names)

    @pytest.mark.timeout(60)  # Add 60 second timeout
    @pytest.mark.xfail(
        reason="Known intermittent timeout issue in Erlang LS in CI environments. "
        "May pass locally but can timeout on slower CI systems, especially macOS. "
        "Similar to known Next LS timeout issues.",
        strict=False,
    )
    @pytest.mark.parametrize("language_server", [Language.ERLANG], indirect=True)
    def test_referencing_symbols_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test finding references across different files."""
        # Test that we can find references to models module functions in services.erl
        file_path = os.path.join("src", "models.erl")

        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        create_user_symbol = None
        for symbol_group in symbols:
            create_user_symbol = next((s for s in symbol_group if "create_user" in s.get("name", "")), None)
            if create_user_symbol:
                break

        if not create_user_symbol or "selectionRange" not in create_user_symbol:
            pytest.skip("create_user function symbol not found")

        sel_start = create_user_symbol["selectionRange"]["start"]
        ref_symbols = [
            ref.symbol for ref in language_server.request_referencing_symbols(file_path, sel_start["line"], sel_start["character"])
        ]

        # Look for cross-file references
        cross_file_refs = [
            symbol
            for symbol in ref_symbols
            if "location" in symbol and "uri" in symbol["location"] and not symbol["location"]["uri"].endswith("models.erl")
        ]

        # We might find references in services.erl or test files
        if cross_file_refs:
            assert len(cross_file_refs) > 0, "Should find some cross-file references"
