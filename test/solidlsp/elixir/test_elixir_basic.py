"""
Basic integration tests for the Elixir language server functionality.

These tests validate the functionality of the language server APIs
like request_references using the test repository.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols
from test.solidlsp.util.diagnostics import assert_file_diagnostics

from . import EXPERT_UNAVAILABLE, EXPERT_UNAVAILABLE_REASON

# These marks will be applied to all tests in this module
pytestmark = [pytest.mark.elixir, pytest.mark.skipif(EXPERT_UNAVAILABLE, reason=f"Next LS not available: {EXPERT_UNAVAILABLE_REASON}")]


class TestElixirBasic:
    """Basic Elixir language server functionality tests."""

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_references_function_definition(self, language_server: SolidLanguageServer):
        """Test finding references to a function definition."""
        file_path = os.path.join("lib", "models.ex")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Find the User module's 'new' function
        user_new_symbol = None
        for symbol in symbols[0]:  # Top level symbols
            if symbol.get("name") == "User" and symbol.get("kind") == 2:  # Module
                for child in symbol.get("children", []):
                    if child.get("name", "").startswith("def new(") and child.get("kind") == 12:  # Function
                        user_new_symbol = child
                        break
                break

        if not user_new_symbol or "selectionRange" not in user_new_symbol:
            pytest.skip("User.new function or its selectionRange not found")

        sel_start = user_new_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])

        assert references is not None
        assert len(references) > 0

        # Should find at least one reference (the definition itself)
        found_definition = any(ref["uri"].endswith("models.ex") for ref in references)
        assert found_definition, "Should find the function definition"

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_references_create_user_function(self, language_server: SolidLanguageServer):
        """Test finding references to create_user function."""
        file_path = os.path.join("lib", "services.ex")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Find the UserService module's 'create_user' function
        create_user_symbol = None
        for symbol in symbols[0]:  # Top level symbols
            if symbol.get("name") == "UserService" and symbol.get("kind") == 2:  # Module
                for child in symbol.get("children", []):
                    if child.get("name", "").startswith("def create_user(") and child.get("kind") == 12:  # Function
                        create_user_symbol = child
                        break
                break

        if not create_user_symbol or "selectionRange" not in create_user_symbol:
            pytest.skip("UserService.create_user function or its selectionRange not found")

        sel_start = create_user_symbol["selectionRange"]["start"]
        references = language_server.request_references(file_path, sel_start["line"], sel_start["character"])

        assert references is not None
        assert len(references) > 0

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_request_referencing_symbols_function(self, language_server: SolidLanguageServer):
        """Test finding symbols that reference a specific function."""
        file_path = os.path.join("lib", "models.ex")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        # Find the User module's 'new' function
        user_new_symbol = None
        for symbol in symbols[0]:  # Top level symbols
            if symbol.get("name") == "User" and symbol.get("kind") == 2:  # Module
                for child in symbol.get("children", []):
                    if child.get("name", "").startswith("def new(") and child.get("kind") == 12:  # Function
                        user_new_symbol = child
                        break
                break

        if not user_new_symbol or "selectionRange" not in user_new_symbol:
            pytest.skip("User.new function or its selectionRange not found")

        sel_start = user_new_symbol["selectionRange"]["start"]
        referencing_symbols = language_server.request_referencing_symbols(file_path, sel_start["line"], sel_start["character"])

        assert referencing_symbols is not None

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_timeout_enumeration_bug(self, language_server: SolidLanguageServer):
        """Test that enumeration doesn't timeout (regression test)."""
        # This should complete without timing out
        symbols = language_server.request_document_symbols("lib/models.ex").get_all_symbols_and_roots()
        assert symbols is not None

        # Test multiple symbol requests in succession
        for _ in range(3):
            symbols = language_server.request_document_symbols("lib/services.ex").get_all_symbols_and_roots()
            assert symbols is not None

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if s["kind"] in {SymbolKind.Module, SymbolKind.Namespace, SymbolKind.Struct}:
                continue

            allow_test_style_name = s["name"].startswith(('test "', 'describe "'))
            allow_struct_name = s["name"].startswith("%")
            allow_type_name = s["name"].startswith("@type ")
            if has_malformed_name(
                s,
                whitespace_allowed=allow_test_style_name or allow_type_name,
                period_allowed=allow_struct_name,
                colon_allowed=allow_test_style_name,
                brace_allowed=allow_test_style_name or allow_struct_name,
                comma_allowed=allow_test_style_name,
            ):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )

    @pytest.mark.parametrize("language_server", [Language.ELIXIR], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "lib/diagnostics_sample.ex",
            (),
            min_count=1,
        )
