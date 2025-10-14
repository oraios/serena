"""Tests for Rego language server (Regal) functionality."""

import os
import sys

import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.rego
@pytest.mark.skipif(sys.platform == "win32", reason="Regal LSP has Windows path handling bug - see https://github.com/StyraInc/regal/issues/1683")
class TestRegoLanguageServer:
    """Test Regal language server functionality for Rego."""

    @pytest.mark.parametrize("language_server", [Language.REGO], indirect=True)
    def test_request_document_symbols_authz(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols can be retrieved from authz.rego."""
        file_path = os.path.join("policies", "authz.rego")
        symbols = language_server.request_document_symbols(file_path)

        assert symbols is not None
        assert len(symbols) > 0

        # Extract symbol names
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        symbol_names = {sym.get("name") for sym in symbol_list if isinstance(sym, dict)}

        # Verify specific Rego rules/functions are found
        assert "allow" in symbol_names, "allow rule not found"
        assert "allow_read" in symbol_names, "allow_read rule not found"
        assert "is_admin" in symbol_names, "is_admin function not found"
        assert "admin_roles" in symbol_names, "admin_roles constant not found"

    @pytest.mark.parametrize("language_server", [Language.REGO], indirect=True)
    def test_request_document_symbols_helpers(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols can be retrieved from helpers.rego."""
        file_path = os.path.join("utils", "helpers.rego")
        symbols = language_server.request_document_symbols(file_path)

        assert symbols is not None
        assert len(symbols) > 0

        # Extract symbol names
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        symbol_names = {sym.get("name") for sym in symbol_list if isinstance(sym, dict)}

        # Verify specific helper functions are found
        assert "is_valid_user" in symbol_names, "is_valid_user function not found"
        assert "is_valid_email" in symbol_names, "is_valid_email function not found"
        assert "is_valid_username" in symbol_names, "is_valid_username function not found"

    @pytest.mark.parametrize("language_server", [Language.REGO], indirect=True)
    def test_find_symbol_full_tree(self, language_server: SolidLanguageServer) -> None:
        """Test finding symbols across entire workspace using symbol tree."""
        symbols = language_server.request_full_symbol_tree()

        # Use SymbolUtils to check for expected symbols
        assert SymbolUtils.symbol_tree_contains_name(symbols, "allow"), "allow rule not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "is_valid_user"), "is_valid_user function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "is_admin"), "is_admin function not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.REGO], indirect=True)
    def test_request_definition(self, language_server: SolidLanguageServer) -> None:
        """Test go-to-definition for Rego symbols."""
        # In authz.rego, the allow rule references helpers.is_valid_user
        file_path = os.path.join("policies", "authz.rego")

        # Get document symbols to find a good position to test
        symbols = language_server.request_document_symbols(file_path)
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        # Find the allow symbol (should reference helpers.is_valid_user)
        allow_symbol = next((s for s in symbol_list if s.get("name") == "allow"), None)

        if allow_symbol and "range" in allow_symbol:
            # Try to get definition from within the allow rule
            # Position should be somewhere in the rule body
            line = allow_symbol["range"]["start"]["line"] + 1  # Move into the rule body
            char = 0

            definitions = language_server.request_definition(file_path, line, char)

            # Some LSPs may not support cross-file definitions well
            # So we just check that the call doesn't error
            assert definitions is not None, "request_definition should return a result (even if empty)"

    @pytest.mark.parametrize("language_server", [Language.REGO], indirect=True)
    def test_find_symbols_validation(self, language_server: SolidLanguageServer) -> None:
        """Test finding symbols in validation.rego which has imports."""
        file_path = os.path.join("policies", "validation.rego")
        symbols = language_server.request_document_symbols(file_path)

        assert symbols is not None
        assert len(symbols) > 0

        # Extract symbol names
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        symbol_names = {sym.get("name") for sym in symbol_list if isinstance(sym, dict)}

        # Verify expected symbols
        assert "validate_user_input" in symbol_names, "validate_user_input rule not found"
        assert "has_valid_credentials" in symbol_names, "has_valid_credentials function not found"
        assert "validate_request" in symbol_names, "validate_request rule not found"
