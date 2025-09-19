"""
Tests for the Nix language server implementation using nixd.

These tests validate symbol finding and cross-file reference capabilities for Nix expressions.
"""

import platform

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

# Skip all Nix tests on Windows as Nix doesn't support Windows
pytestmark = pytest.mark.skipif(platform.system() == "Windows", reason="Nix and nil are not available on Windows")


@pytest.mark.nix
class TestNixLanguageServer:
    """Test Nix language server symbol finding capabilities."""

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_find_symbols_in_default_nix(self, language_server: SolidLanguageServer) -> None:
        """Test finding specific symbols in default.nix."""
        symbols = language_server.request_document_symbols("default.nix")

        assert symbols is not None
        assert len(symbols) > 0

        # Extract symbol names from the returned structure
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        symbol_names = {sym.get("name") for sym in symbol_list if isinstance(sym, dict)}

        # Verify specific function exists
        assert "makeGreeting" in symbol_names, "makeGreeting function not found"

        # Verify exact attribute sets are found
        expected_attrs = {"listUtils", "stringUtils"}
        found_attrs = symbol_names & expected_attrs
        assert found_attrs == expected_attrs, f"Expected exactly {expected_attrs}, found {found_attrs}"

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_find_symbols_in_utils(self, language_server: SolidLanguageServer) -> None:
        """Test finding symbols in lib/utils.nix."""
        symbols = language_server.request_document_symbols("lib/utils.nix")

        assert symbols is not None
        assert len(symbols) > 0

        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        symbol_names = {sym.get("name") for sym in symbol_list if isinstance(sym, dict)}

        # Verify exact utility modules are found
        expected_modules = {"math", "strings", "lists", "attrs"}
        found_modules = symbol_names & expected_modules
        assert found_modules == expected_modules, f"Expected exactly {expected_modules}, found {found_modules}"

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_find_symbols_in_flake(self, language_server: SolidLanguageServer) -> None:
        """Test finding symbols in flake.nix."""
        symbols = language_server.request_document_symbols("flake.nix")

        assert symbols is not None
        assert len(symbols) > 0

        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        symbol_names = {sym.get("name") for sym in symbol_list if isinstance(sym, dict)}

        # Flakes must have either inputs or outputs
        assert "inputs" in symbol_names or "outputs" in symbol_names, "Flake must have inputs or outputs"

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_find_symbols_in_module(self, language_server: SolidLanguageServer) -> None:
        """Test finding symbols in a NixOS module."""
        symbols = language_server.request_document_symbols("modules/example.nix")

        assert symbols is not None
        assert len(symbols) > 0

        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        symbol_names = {sym.get("name") for sym in symbol_list if isinstance(sym, dict)}

        # NixOS modules must have either options or config
        assert "options" in symbol_names or "config" in symbol_names, "Module must have options or config"

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        """Test finding references within the same file."""
        symbols = language_server.request_document_symbols("default.nix")

        assert symbols is not None
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        # Find makeGreeting function
        greeting_symbol = None
        for sym in symbol_list:
            if sym.get("name") == "makeGreeting":
                greeting_symbol = sym
                break

        assert greeting_symbol is not None, "makeGreeting function not found"
        assert "range" in greeting_symbol, "Symbol must have range information"

        range_start = greeting_symbol["range"]["start"]
        refs = language_server.request_references("default.nix", range_start["line"], range_start["character"])

        assert refs is not None
        assert isinstance(refs, list)
        # nixd finds at least the inherit statement (line 67)
        assert len(refs) >= 1, f"Should find at least 1 reference to makeGreeting, found {len(refs)}"

        # Verify makeGreeting is referenced at expected locations
        if refs:
            ref_lines = sorted([ref["range"]["start"]["line"] for ref in refs])
            # Check if we found the inherit (line 67, 0-indexed: 66)
            assert 66 in ref_lines, f"Should find makeGreeting inherit at line 67, found at lines {[l+1 for l in ref_lines]}"

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_hover_information(self, language_server: SolidLanguageServer) -> None:
        """Test hover information for symbols."""
        # Get hover info for makeGreeting function
        hover_info = language_server.request_hover("default.nix", 9, 5)  # Position near makeGreeting

        assert hover_info is not None, "Should provide hover information"

        if isinstance(hover_info, dict) and len(hover_info) > 0:
            # If hover info is provided, it should have proper structure
            assert "contents" in hover_info or "value" in hover_info, "Hover should have contents or value"

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_cross_file_references_utils_import(self, language_server: SolidLanguageServer) -> None:
        """Test finding cross-file references for imported utils."""
        # Find references to 'utils' which is imported in default.nix from lib/utils.nix
        # Line 10 in default.nix: utils = import ./lib/utils.nix { inherit lib; };
        refs = language_server.request_references("default.nix", 9, 2)  # Position of 'utils'

        assert refs is not None
        assert isinstance(refs, list)

        # Should find references within default.nix where utils is used
        default_refs = [ref for ref in refs if "default.nix" in ref.get("uri", "")]
        # utils is: imported (line 10), used in listUtils.unique (line 24), inherited in exports (line 69)
        assert len(default_refs) >= 2, f"Should find at least 2 references to utils in default.nix, found {len(default_refs)}"

        # Verify utils is referenced at expected locations (0-indexed)
        if default_refs:
            ref_lines = sorted([ref["range"]["start"]["line"] for ref in default_refs])
            # Check for key references - at least the import (line 10) or usage (line 24)
            assert (
                9 in ref_lines or 23 in ref_lines
            ), f"Should find utils import or usage, found references at lines {[l+1 for l in ref_lines]}"

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_verify_imports_exist(self, language_server: SolidLanguageServer) -> None:
        """Verify that our test files have proper imports set up."""
        # Verify that default.nix imports utils from lib/utils.nix
        symbols = language_server.request_document_symbols("default.nix")

        assert symbols is not None
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        # Check that makeGreeting exists (defined in default.nix)
        symbol_names = {sym.get("name") for sym in symbol_list if isinstance(sym, dict)}
        assert "makeGreeting" in symbol_names, "makeGreeting should be found in default.nix"

        # Verify lib/utils.nix has the expected structure
        utils_symbols = language_server.request_document_symbols("lib/utils.nix")
        assert utils_symbols is not None
        utils_list = utils_symbols[0] if isinstance(utils_symbols, tuple) else utils_symbols
        utils_names = {sym.get("name") for sym in utils_list if isinstance(sym, dict)}

        # Verify key functions exist in utils
        assert "math" in utils_names, "math should be found in lib/utils.nix"
        assert "strings" in utils_names, "strings should be found in lib/utils.nix"

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_go_to_definition_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test go-to-definition from default.nix to lib/utils.nix."""
        # Line 24 in default.nix: unique = utils.lists.unique;
        # Test go-to-definition for 'utils'
        definitions = language_server.request_definition("default.nix", 23, 14)  # Position of 'utils'

        assert definitions is not None
        assert isinstance(definitions, list)

        if len(definitions) > 0:
            # Should point to the import statement or utils.nix
            assert any(
                "utils" in def_item.get("uri", "") or "default.nix" in def_item.get("uri", "") for def_item in definitions
            ), "Definition should relate to utils import or utils.nix file"

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_definition_navigation_in_flake(self, language_server: SolidLanguageServer) -> None:
        """Test definition navigation in flake.nix."""
        # Test that we can navigate to definitions within flake.nix
        # Line 69: default = hello-custom;
        definitions = language_server.request_definition("flake.nix", 68, 20)  # Position of 'hello-custom'

        assert definitions is not None
        assert isinstance(definitions, list)
        # nixd should find the definition of hello-custom in the same file
        if len(definitions) > 0:
            assert any(
                "flake.nix" in def_item.get("uri", "") for def_item in definitions
            ), "Should find hello-custom definition in flake.nix"

    @pytest.mark.parametrize("language_server", [Language.NIX], indirect=True)
    def test_full_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        """Test that full symbol tree is not empty."""
        symbols = language_server.request_full_symbol_tree()

        assert symbols is not None
        assert len(symbols) > 0, "Symbol tree should not be empty"

        # The tree should have at least one root node
        root = symbols[0]
        assert isinstance(root, dict), "Root should be a dict"
        assert "name" in root, "Root should have a name"
