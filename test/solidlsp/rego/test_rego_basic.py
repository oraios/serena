"""Tests for Rego language server (Regal) functionality."""

import os
import sys

import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.rego
@pytest.mark.skipif(
    sys.platform == "win32", reason="Regal LSP has Windows path handling bug - see https://github.com/StyraInc/regal/issues/1683"
)
class TestRegoLanguageServer:
    """Test Regal language server functionality for Rego."""

    @pytest.mark.parametrize("language_server", [Language.REGO], indirect=True)
    def test_request_document_symbols_authz(self, language_server: SolidLanguageServer) -> None:
        """Test that document symbols can be retrieved from authz.rego."""
        file_path = os.path.join("policies", "authz.rego")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

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
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

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
    def test_request_definition_within_file(self, language_server: SolidLanguageServer) -> None:
        """Test go-to-definition for symbols within the same file."""
        # In authz.rego, check_permission references admin_roles
        file_path = os.path.join("policies", "authz.rego")

        # Get document symbols
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        # Find the is_admin symbol which references admin_roles
        is_admin_symbol = next((s for s in symbol_list if s.get("name") == "is_admin"), None)
        assert is_admin_symbol is not None, "is_admin symbol should always be found in authz.rego"
        assert "range" in is_admin_symbol, "is_admin symbol should have a range"

        # Request definition from within is_admin (line 25, which references admin_roles at line 21)
        # Line 25 is: admin_roles[_] == user.role
        line = is_admin_symbol["range"]["start"]["line"] + 1
        char = 4  # Position at "admin_roles"

        definitions = language_server.request_definition(file_path, line, char)
        assert definitions is not None and len(definitions) > 0, "Should find definition for admin_roles"

        # Verify the definition points to admin_roles in the same file
        assert any("authz.rego" in defn.get("relativePath", "") for defn in definitions), "Definition should be in authz.rego"

    @pytest.mark.parametrize("language_server", [Language.REGO], indirect=True)
    def test_request_definition_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test go-to-definition for symbols across files (cross-file references)."""
        # In authz.rego line 11, the allow rule calls utils.is_valid_user
        # This function is defined in utils/helpers.rego
        file_path = os.path.join("policies", "authz.rego")

        # Get document symbols
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        # Find the allow symbol
        allow_symbol = next((s for s in symbol_list if s.get("name") == "allow"), None)
        assert allow_symbol is not None, "allow symbol should always be found in authz.rego"
        assert "range" in allow_symbol, "allow symbol should have a range"

        # Request definition from line 11 where utils.is_valid_user is called
        # Line 11: utils.is_valid_user(input.user)
        line = 10  # 0-indexed, so line 11 in file is line 10 in LSP
        char = 7  # Position at "is_valid_user" in "utils.is_valid_user"

        definitions = language_server.request_definition(file_path, line, char)
        assert definitions is not None and len(definitions) > 0, "Should find cross-file definition for is_valid_user"

        # Verify the definition points to helpers.rego (cross-file)
        assert any(
            "helpers.rego" in defn.get("relativePath", "") for defn in definitions
        ), "Definition should be in utils/helpers.rego (cross-file reference)"

    @pytest.mark.parametrize("language_server", [Language.REGO], indirect=True)
    def test_find_symbols_validation(self, language_server: SolidLanguageServer) -> None:
        """Test finding symbols in validation.rego which has imports."""
        file_path = os.path.join("policies", "validation.rego")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()

        assert symbols is not None
        assert len(symbols) > 0

        # Extract symbol names
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        symbol_names = {sym.get("name") for sym in symbol_list if isinstance(sym, dict)}

        # Verify expected symbols
        assert "validate_user_input" in symbol_names, "validate_user_input rule not found"
        assert "has_valid_credentials" in symbol_names, "has_valid_credentials function not found"
        assert "validate_request" in symbol_names, "validate_request rule not found"
